"""Tests for task-breakdown-drafter.py hook."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))


def _load_hook_module():
    """Load task-breakdown-drafter.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / "task-breakdown-drafter.py"
    spec = importlib.util.spec_from_file_location("task_breakdown_drafter", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drafter = _load_hook_module()


def _run_main(hook_input: dict, capsys) -> dict:
    stdin = io.StringIO(json.dumps(hook_input))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "stdin", stdin)
        drafter.main()
    return json.loads(capsys.readouterr().out)


def test_main_permissionModeIsPlan_silentNoop(capsys):
    hook_input = {
        "permission_mode": "plan",
        "prompt": "Refactor the auth middleware to use JWT and update every endpoint.",
    }

    result = _run_main(hook_input, capsys)

    assert result == {}


@pytest.mark.parametrize("prompt", ["", "   "])
def test_main_emptyPrompt_silentNoop(prompt, capsys):
    hook_input = {"permission_mode": "default", "prompt": prompt}

    result = _run_main(hook_input, capsys)

    assert result == {}


def test_main_normalPrompt_injectsStaticReminder(capsys):
    hook_input = {"permission_mode": "default", "prompt": "fix typo in README"}

    result = _run_main(hook_input, capsys)

    assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "non-binding" in context.lower()
    assert "explore" in context.lower() or "research" in context.lower()


def test_main_normalPrompt_remindsToCheckExistingTasksForConflicts(capsys):
    hook_input = {"permission_mode": "default", "prompt": "fix typo in README"}

    result = _run_main(hook_input, capsys)

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "tasklist" in context.lower()
    assert "subtask" in context.lower()


def test_main_normalPrompt_systemMessageIncludesPluginVersion(capsys):
    hook_input = {"permission_mode": "default", "prompt": "fix typo in README"}
    expected_version = drafter.plugin_version()

    result = _run_main(hook_input, capsys)

    assert expected_version != "unknown"
    assert f"task-seeder v{expected_version}" in result["systemMessage"]


def test_pluginVersion_manifestMissing_returnsUnknown(monkeypatch, tmp_path):
    monkeypatch.setattr(drafter, "PLUGIN_ROOT", tmp_path)

    assert drafter.plugin_version() == "unknown"


def test_main_missingPermissionMode_stillInjectsReminder(capsys):
    """No permission_mode key (older CC version) must fall through to normal behavior,
    not be treated as plan mode."""
    hook_input = {"prompt": "Migrate the payment service to Adyen and add tests."}

    result = _run_main(hook_input, capsys)

    assert "additionalContext" in result["hookSpecificOutput"]


def test_reminder_isSameEveryTime_noHeuristicGating(capsys):
    """Static reminder: identical output regardless of prompt content — no gating,
    the model decides whether it actually applies."""
    single_action_input = {"permission_mode": "default", "prompt": "fix typo"}
    multi_action_input = {
        "permission_mode": "default",
        "prompt": "Investigate why the login flow fails, then fix it and add tests.",
    }

    single_result = _run_main(single_action_input, capsys)
    multi_result = _run_main(multi_action_input, capsys)

    assert (
        single_result["hookSpecificOutput"]["additionalContext"]
        == multi_result["hookSpecificOutput"]["additionalContext"]
    )
