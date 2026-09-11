"""Both hosts use the custom classifier and the same Claude prompt policy."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOK))


@pytest.fixture
def judge(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.delenv("PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("AGENT_RUNTIME", "claude")
    monkeypatch.setenv("PERMISSIONS_JUDITOR_WATCHED_COMMANDS", "python3,mcp__example__*")
    source = tmp_path / "claude/settings.json"
    source.parent.mkdir()
    source.write_text(json.dumps({"permissions": {
        "allow": ["Bash(ls *)", "mcp__example__read"],
        "ask": ["Bash(python3 *)", "mcp__example__write"],
        "deny": ["Bash(rm -rf *)", "mcp__example__delete"]},
        "autoMode": {"environment": ["shared-environment"], "allow": ["shared-allow"],
                     "soft_deny": ["shared-soft-deny"], "hard_deny": ["shared-hard-deny"]}}))
    spec = importlib.util.spec_from_file_location("shared_judge_test", HOOK / "security-judge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("decision", ["allow", "ask", "deny"])
@pytest.mark.parametrize("tool", ["Bash", "mcp__example__read"])
def test_shared_classifier_and_prompt_policy(judge, monkeypatch, tmp_path, runtime, decision, tool):
    monkeypatch.setenv("AGENT_RUNTIME", runtime)
    calls = []
    class Client:
        @staticmethod
        def has_credentials(): return True
        @staticmethod
        def from_env(**kwargs): return Client()
        def complete_with_tool(self, **kwargs):
            calls.append(kwargs)
            return {"decision": decision, "reasoning": "classifier reason"}
    monkeypatch.setattr(judge, "AnthropicClient", Client)
    inputs = {"command": "python3 -c 'print(1)'"} if tool == "Bash" else {"query": "SELECT 1"}
    result = judge.run(json.dumps({"tool_name": tool, "tool_input": inputs, "cwd": str(tmp_path)}))
    assert len(calls) == 1
    system = calls[0]["system"]
    for value in ["shared-environment", "shared-allow", "shared-soft-deny", "shared-hard-deny"]:
        assert value in system
    assert ("Bash(rm -rf *)" if tool == "Bash" else "mcp__example__delete") in system
    assert judge.SETTINGS_PATH == tmp_path / "claude/settings.json"
    output = result["hookSpecificOutput"]
    assert output["hookEventName"] == "PermissionRequest"
    if runtime == "codex" and decision == "ask":
        assert output["decision"] == {
            "behavior": "deny",
            "message": "[permissions-juditor] Classifier requested review; blocked in Codex: classifier reason",
        }
    else:
        assert output["decision"]["behavior"] == decision
    log = tmp_path / runtime / "permissions-juditor/decisions.jsonl"
    assert json.loads(log.read_text())["decision"] == decision


def test_codex_policy_reloaded_for_next_request(judge, monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME", "codex")
    assert judge.load_auto_mode_context()["environment"] == ["shared-environment"]
    judge.SETTINGS_PATH.write_text('{"autoMode":{"environment":["changed-policy"]}}')
    assert judge.load_auto_mode_context()["environment"] == ["changed-policy"]


@pytest.mark.parametrize("failure", ["credentials", "network", "invalid"])
def test_codex_classifier_failure_never_allows(judge, monkeypatch, failure):
    monkeypatch.setenv("AGENT_RUNTIME", "codex")
    class Client:
        @staticmethod
        def has_credentials(): return failure != "credentials"
        @staticmethod
        def from_env(**kwargs): return Client()
        def complete_with_tool(self, **kwargs):
            if failure == "network": raise OSError("offline")
            return {"decision": "unknown"}
    monkeypatch.setattr(judge, "AnthropicClient", Client)
    assert judge.run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "python3 script.py"}})) == {}


def test_invalid_runtime_main_defers(judge):
    env = dict(os.environ, AGENT_RUNTIME="invalid")
    result = subprocess.run([sys.executable, str(HOOK / "security-judge.py")], input="{}", capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
