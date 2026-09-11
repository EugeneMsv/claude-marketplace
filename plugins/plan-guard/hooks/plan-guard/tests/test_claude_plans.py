import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOK))
spec = importlib.util.spec_from_file_location("claude_plan_sync", HOOK / "plan-sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
from plan_storage import archive, associations


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME", "claude")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    (tmp_path / "config/plans").mkdir(parents=True)


def write_plan(tmp_path):
    plan = tmp_path / "config/plans/example.md"
    plan.write_text("original plan")
    project = tmp_path / "project"
    project.mkdir()
    return plan, project


def event(source, project, tool="Write"):
    return {"hook_event_name": "PostToolUse", "tool_name": tool, "cwd": str(project), "tool_input": {"file_path": str(source)}}


def test_sync_and_updates(tmp_path):
    source, project = write_plan(tmp_path)
    sync.run(event(source, project))
    destination = project / ".claude/plans/example.md"
    assert destination.read_text() == "original plan"
    source.write_text("updated plan")
    sync.run(event(source, project, "Edit"))
    assert destination.read_text() == "updated plan"
    assert associations(source.parent) == {"example.md": str(project)}


def test_project_isolation(tmp_path):
    source, project = write_plan(tmp_path)
    sync.run(event(source, project))
    other = tmp_path / "other"
    other.mkdir()
    sync.run(event(source, other))
    assert not (other / ".claude").exists()


def test_exit_plan_mode_and_global_cwd(tmp_path):
    source, project = write_plan(tmp_path)
    sync.run(event(source, project, "ExitPlanMode"))
    source.write_text("updated")
    sync.run(event(source, tmp_path / "config", "ExitPlanMode"))
    assert (project / ".claude/plans/example.md").read_text() == "updated"


def test_unrelated_file_not_copied(tmp_path):
    source, project = write_plan(tmp_path)
    outside = tmp_path / "unrelated.md"
    outside.write_text("not a plan")
    sync.run(event(outside, project))
    assert not (project / ".claude").exists()


def test_git_root_detection(tmp_path):
    source, project = write_plan(tmp_path)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    nested = project / "src"
    nested.mkdir()
    sync.run(event(source, nested))
    assert (project / ".claude/plans/example.md").is_file()
    assert not (nested / ".claude").exists()


def test_archive_preserves_content_and_updates_metadata(tmp_path):
    source, project = write_plan(tmp_path)
    sync.run(event(source, project))
    os.utime(source, (0, 0))
    metadata = (source.parent / ".metadata").read_text()
    assert archive("2w", True) == 1
    assert source.exists()
    assert (source.parent / ".metadata").read_text() == metadata
    assert archive("2w") == 1
    [global_copy] = source.parent.glob("archive/*/*.md")
    [project_copy] = (project / ".claude/plans").glob("archive/*/*.md")
    assert global_copy.read_text() == project_copy.read_text() == "original plan"
    assert associations(source.parent) == {}


def test_legacy_metadata_and_log_retention(tmp_path):
    source, project = write_plan(tmp_path)
    (tmp_path / "config/plan-projects.json").write_text(json.dumps({"example.md": str(project)}))
    sync.run(event(source, project))
    assert (source.parent / ".metadata").exists()
    assert (tmp_path / "config/plan-projects.json").exists()
    logs = tmp_path / "config/logs"
    logs.mkdir()
    (logs / "hook.log").write_text("2000-01-01 old\nunknown timestamp\n")
    archive("2w")
    assert (logs / "hook.log").read_text() == "unknown timestamp\n"


def test_symlink_destination_rejected(tmp_path):
    source, project = write_plan(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".claude").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        sync.run(event(source, project))
    assert not list(outside.rglob("*.md"))
