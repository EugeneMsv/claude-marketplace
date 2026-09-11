import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOK))
spec = importlib.util.spec_from_file_location("codex_plans", HOOK / "plan-sync.py")
plans = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plans)
from plan_storage import archive


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME", "codex")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.delenv("PLUGIN_DATA", raising=False)


def event(project, session="one"):
    project.mkdir(exist_ok=True)
    return {"hook_event_name": "PostToolUse", "tool_name": "update_plan", "cwd": str(project), "session_id": session,
            "tool_input": {"plan": [{"step": "Inspect", "status": "completed"}, {"step": "Verify", "status": "pending"}]}}


def test_snapshot_and_session_isolation(tmp_path):
    project = tmp_path / "project"
    plans.snapshot_codex(event(project))
    plans.snapshot_codex(event(project))
    plans.snapshot_codex(event(project, "two"))
    paths = list(project.glob(".Codex/plan-guard/plans/*.md"))
    assert len(paths) == 2
    assert "[x] Inspect" in paths[0].read_text()
    assert not (tmp_path / ".claude").exists()


def test_archive_collision_and_content(tmp_path):
    project = tmp_path / "project"
    plans.snapshot_codex(event(project))
    [path] = project.glob(".Codex/plan-guard/plans/*.md")
    content = path.read_text()
    os.utime(path, (0, 0))
    assert archive("2w", dry_run=True) == 1
    assert path.exists()
    assert archive("2w") == 1
    archived = list(path.parent.glob("archive/*/*.md"))
    assert len(archived) == 1 and archived[0].read_text() == content
    path.write_text("second version")
    os.utime(path, (0, 0))
    assert archive("2w") == 1
    assert sorted(p.read_text() for p in path.parent.glob("archive/*/*.md")) == sorted([content, "second version"])
    assert archive("2w") == 0


def test_recent_plan_preserved(tmp_path):
    project = tmp_path / "project"
    plans.snapshot_codex(event(project))
    assert archive("2w") == 0


@pytest.mark.parametrize("age", ["0d", "-1d", "2years", "", "x"])
def test_invalid_age(age):
    with pytest.raises(ValueError):
        archive(age)


def test_symlink_output_rejected(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (project / ".Codex").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError):
        plans.snapshot_codex(event(project))
    assert not list(elsewhere.rglob("*.md"))


def test_unsupported_tool_not_snapshotted(tmp_path):
    data = event(tmp_path / "project")
    data["tool_name"] = "apply_patch"
    plans.snapshot_codex(data)
    assert not list(tmp_path.rglob("*.md"))


def test_codex_enforcer_uses_native_reference(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("codex_enforcer", HOOK / "plan-mode-enforcer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.AnthropicClient, "has_credentials", lambda: pytest.fail("no API for Codex guidance"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "UserPromptSubmit", "permission_mode": "plan"})))
    module.main()
    result = json.loads(capsys.readouterr().out)
    assert "Codex planning guidance" in result["hookSpecificOutput"]["additionalContext"]


def test_non_plan_prompt_is_noop(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("codex_enforcer_other", HOOK / "plan-mode-enforcer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"hook_event_name":"UserPromptSubmit","permission_mode":"default"}'))
    module.main()
    assert json.loads(capsys.readouterr().out) == {}


def test_failed_plan_update_not_saved(tmp_path):
    data = event(tmp_path / "project")
    data["tool_response"] = {"isError": True}
    plans.snapshot_codex(data)
    assert not list(tmp_path.rglob("*.md"))
