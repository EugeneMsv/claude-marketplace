#!/usr/bin/env python3
"""UserPromptSubmit/PreToolUse hook — injects project-specific planning requirements."""

import json
import os
import sys
from pathlib import Path

from anthropic_client import AnthropicClient

BUILD_FILE_HINTS = {
    "build.gradle": "Gradle (Java/Kotlin)",
    "build.gradle.kts": "Gradle Kotlin DSL",
    "pom.xml": "Maven",
    "package.json": "Node.js/npm",
    "requirements.txt": "Python/pip",
    "pyproject.toml": "Python/pyproject",
    "go.mod": "Go modules",
    "Makefile": "Make",
    "Cargo.toml": "Rust/Cargo",
    "MODULE.bazel": "Bazel",
    "WORKSPACE.bazel": "Bazel",
    "WORKSPACE": "Bazel",
    "BUILD.bazel": "Bazel",
}

PROMPT_TEMPLATE = """\
You are a planning assistant for a software engineer. Based on the project context below, \
produce a concise systemMessage (plain-text bullet points) that the engineer will see \
when entering plan mode. The message must specify:

0. That the plan MUST begin with a table of contents listing all tasks at the top
1. That the FIRST task is optional git prep: stash unchanged work, switch to master/main, \
pull latest, then create a new feature branch — auto-suggest the branch name from the Jira \
ticket if one is present in the context(example TASK-123-logger-improvement, where TASK-123 - is jira ticket),\
otherwise ask for it. "Optional" means the plan \
must ASK the user during planning to confirm whether this git-prep task is required, and \
include or omit it based on their answer
2. That EVERY task's verification uses exact, directly-runnable CLI commands — not a vague \
phrase like "build + test". Give the literal build and test invocations scoped to that task \
(e.g. `bazel test //path/to:FooTest` or `gradle :module:test --tests '*.FooTest'`)
3. That every task must end with a git commit in format "Task N: <description>"
4. That the SECOND-TO-LAST task must EXHAUSTIVELY DISCOVER every LOCAL verification that \
exists in this project's SDLC — scan the code, build files, local scripts, and existing memory \
(NOT CI pipeline files) to identify ALL local verification phases (unit, integration, e2e/UAT, \
smoke, contract, lint, etc.). Finding one type does NOT end the search: keep looking for every \
other type. For each type found, list the EXACT, directly-runnable command (or the local \
script/doc reference that runs it). List them as ORDERED, SEPARATE phases — unit first, then \
integration, then e2e/smoke, etc. For any type NOT found after searching, state it explicitly, \
e.g. "unit tests: not found, nothing to run" — never silently skip. This task IDENTIFIES how \
to run each local verification, not merely "run the tests"
5. That relevant documentation must be IDENTIFIED during planning (specific files/pages, \
e.g. README.md, CLAUDE.md, a Confluence page), and the LAST task must explicitly NAME which \
of those documents to update for this change — not a generic "update documentation"

Be specific — use the actual commands from the project context. If you cannot determine \
the exact command, use a sensible default for the detected build tool.
Output ONLY the bullet-point message, no preamble.

PROJECT CONTEXT:
{context}
"""


def collect_context(cwd: str) -> tuple[str, list[str]]:
    """Return (context_for_model, discoveries) where discoveries are short human-readable
    notes on what was found, used to summarize the status line."""
    base = Path(cwd)
    parts = []
    discoveries = []

    # Detected build tools (deduped — several markers can map to one tool, e.g. Bazel)
    found_tools = list(
        dict.fromkeys(
            label for fname, label in BUILD_FILE_HINTS.items() if (base / fname).exists()
        )
    )
    if found_tools:
        parts.append(f"Build tools: {', '.join(found_tools)}")
        discoveries.append(f"build tooling ({', '.join(found_tools)})")

    # CLAUDE.md or .claude/CLAUDE.md — first 60 lines
    for candidate in [base / "CLAUDE.md", base / ".claude" / "CLAUDE.md"]:
        if candidate.exists():
            try:
                lines = candidate.read_text(errors="ignore").splitlines()[:60]
                parts.append("CLAUDE.md:\n" + "\n".join(lines))
                discoveries.append(f"project instructions ({candidate.name})")
            except OSError:
                pass
            break

    # key-commands.md
    for candidate in [
        base / ".claude" / "rules" / "key-commands.md",
        Path.home() / ".claude" / "rules" / "key-commands.md",
    ]:
        if candidate.exists():
            try:
                parts.append(f"key-commands.md:\n{candidate.read_text(errors='ignore')[:600]}")
                discoveries.append("key build/test commands")
            except OSError:
                pass
            break

    return "\n\n".join(parts)[:1200], discoveries


def build_requirements_message(client: AnthropicClient, context: str) -> str:
    """Generate the planning requirements via a cheap classification-tier model."""
    # ANTHROPIC_MODEL is a CLI alias ("opus"), not a real model id — resolve a concrete one.
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    return client.complete(model=model, prompt=PROMPT_TEMPLATE.format(context=context), max_tokens=2000)


def main() -> None:
    if not AnthropicClient.has_credentials():
        print(json.dumps({"systemMessage": "[plan-enforcer] No credentials detected, skipping"}))
        return

    hook_input = json.load(sys.stdin)
    hook_event = hook_input.get("hook_event_name", "PreToolUse")
    cwd = hook_input.get("cwd", os.getcwd())

    # For UserPromptSubmit, only activate when actually in plan mode
    if hook_event == "UserPromptSubmit" and hook_input.get("permission_mode") != "plan":
        print("{}")
        return

    try:
        context, discoveries = collect_context(cwd)
        system_message = build_requirements_message(AnthropicClient.from_env(), context)
        found = ", ".join(discoveries) if discoveries else "no project files"
        status_line = (
            "[plan-enforcer] ✅ AI-generated requirements loaded. "
            f"Discovered {found} in {Path(cwd).name}. "
            "Tailored verification, branch-prep, and doc-update tasks accordingly.\n"
            "--- injected into context ---\n"
            f"{system_message}"
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "systemMessage": (
                "[plan-enforcer] ❌ Failed to generate requirements — skipping. "
                f"{type(exc).__name__}: {exc}"
            )
        }))
        return

    output = {
        "systemMessage": status_line,
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": system_message,
        },
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
