#!/usr/bin/env python3
"""Synchronize Claude plan files or persist explicit Codex plan updates."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from agent_runtime import agent_home, data_dir, runtime_name
from plan_storage import locked, atomic_write, associations, save_associations


def snapshot_codex(event):
    if event.get("hook_event_name") != "PostToolUse" or event.get("tool_name") != "update_plan":
        return
    response = event.get("tool_response")
    if event.get("error") or (isinstance(response, dict) and (response.get("isError") or response.get("error"))):
        return
    inputs = event.get("tool_input") or {}
    plan = inputs.get("plan") if isinstance(inputs, dict) else None
    if not isinstance(plan, list) or not plan:
        return
    if not all(isinstance(item, dict) and isinstance(item.get("step"), str) and item.get("status") in {"pending", "in_progress", "completed"} for item in plan):
        return
    cwd = event.get("cwd")
    session = event.get("session_id")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute() or not session:
        return
    project = Path(cwd).resolve()
    directory = project / ".Codex/plan-guard/plans"
    for path in [project / ".Codex", directory.parent, directory]:
        if path.is_symlink():
            raise ValueError("Refusing symlinked plan output directory")
    key = hashlib.sha256((str(project) + str(session)).encode()).hexdigest()[:20]
    symbols = {"pending": "[ ]", "in_progress": "[-]", "completed": "[x]"}
    text = "# Plan snapshot\n\n" + str(inputs.get("explanation") or "") + "\n\n"
    text += "\n".join(f"- {symbols[item['status']]} {item['step']}" for item in plan) + "\n"
    with locked(directory):
        atomic_write(directory / (key + ".md"), text)
    state = data_dir("plan-guard")
    with locked(state):
        index = state / "projects.json"
        projects = json.loads(index.read_text()) if index.exists() else []
        if not isinstance(projects, list):
            raise ValueError("Invalid project index")
        atomic_write(index, json.dumps(sorted(set(projects + [str(project)]))) + "\n")



def sync_claude(event):
    if event.get("hook_event_name") != "PostToolUse":
        return
    tool = event.get("tool_name")
    if tool not in {"Write", "Edit", "ExitPlanMode"}:
        return
    home = agent_home().resolve()
    plans = home / "plans"
    if not plans.is_dir() or plans.is_symlink():
        return
    if tool == "ExitPlanMode":
        candidates = [p for p in plans.glob("*.md") if p.is_file() and not p.is_symlink()]
        if not candidates:
            return
        source = max(candidates, key=lambda p: p.stat().st_mtime)
    else:
        inputs = event.get("tool_input") or {}
        filename = inputs.get("file_path") if isinstance(inputs, dict) else None
        if not isinstance(filename, str):
            return
        source = Path(filename)
        if source.parent.resolve() != plans.resolve() or source.suffix != ".md" or source.is_symlink() or not source.is_file():
            return
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return
    project = Path(cwd).resolve()
    result = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        project = Path(result.stdout.strip()).resolve()
    with locked(plans):
        mapping = associations(plans)
        associated = mapping.get(source.name)
        if project == home:
            if not associated:
                return
            project = Path(associated)
        if associated and Path(associated).resolve() != project.resolve():
            return
        if not project.is_absolute() or not project.is_dir():
            return
        target = project / ".claude/plans"
        if any(p.is_symlink() for p in [project, project / ".claude", target]):
            raise ValueError("Refusing symlinked plan destination")
        target.mkdir(parents=True, exist_ok=True)
        destination = target / source.name
        if destination.resolve() == source.resolve():
            return
        atomic_write(destination, source.read_text())
        mapping[source.name] = str(project)
        save_associations(plans, mapping)


def run(event):
    if runtime_name() == "codex":
        snapshot_codex(event)
    else:
        sync_claude(event)


if __name__ == "__main__":
    try:
        event = json.load(sys.stdin)
        if isinstance(event, dict):
            run(event)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"plan-guard: {type(error).__name__}", file=sys.stderr)
    print("{}")
