import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOK))
def load_detector(name):
    spec = importlib.util.spec_from_file_location(name + "_detector", HOOK / (name + "-detector.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_detector("tool")
prompt = load_detector("prompt")
fail = load_detector("fail")


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.delenv("PLUGIN_DATA", raising=False)
    monkeypatch.delenv("PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("AGENT_RUNTIME", "claude")
    monkeypatch.setenv("FEEDBACK_LOOP_LOG_PROMPTS", "0")


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_tool_logs_are_isolated(runtime, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME", runtime)
    tool.record({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status"}})
    [log] = (tmp_path / runtime / "feedback-loop").glob("*.jsonl")
    assert json.loads(log.read_text())["command"] == "git status"
    assert not (tmp_path / ("codex" if runtime == "claude" else "claude")).exists()
    assert log.stat().st_mode & 0o077 == 0


def test_prompt_opt_in_and_empty_skip(monkeypatch, tmp_path):
    event = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "session_id": "session"}
    prompt.record(event)
    assert not list(tmp_path.rglob("*.jsonl"))
    monkeypatch.setenv("FEEDBACK_LOOP_LOG_PROMPTS", "1")
    prompt.record(event)
    prompt.record(dict(event, prompt="  "))
    [log] = tmp_path.rglob("*.jsonl")
    assert len(log.read_text().splitlines()) == 1
    assert json.loads(log.read_text())["session_id"] == "session"


@pytest.mark.parametrize("response", [{"exit_code": 2, "output": "failed"}, {"isError": True}, "Process exited with code 1\nfailed", "Exit code: 3"])
def test_codex_failures(response, tmp_path):
    fail.record({"hook_event_name": "PostToolUse", "tool_response": response})
    assert (tmp_path / "claude/feedback-loop/fails.jsonl").exists()


@pytest.mark.parametrize("response", [{"exit_code": 0}, {"isError": False}, "error is an example word", None])
def test_success_or_unknown_is_not_failure(response, tmp_path):
    fail.record({"hook_event_name": "PostToolUse", "tool_response": response})
    assert not list(tmp_path.rglob("*.jsonl"))


def test_claude_failure(tmp_path):
    fail.record({"hook_event_name": "PostToolUseFailure", "error": "tool failed"})
    assert (tmp_path / "claude/feedback-loop/fails.jsonl").exists()


def test_runtime_override_and_validation():
    from agent_runtime import runtime_name
    assert runtime_name({"PLUGIN_ROOT": "/plugins/example"}) == "codex"
    assert runtime_name({"PLUGIN_ROOT": "/plugins/example", "AGENT_RUNTIME": "claude"}) == "claude"
    with pytest.raises(ValueError):
        runtime_name({"AGENT_RUNTIME": "other"})


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("custom_home", [False, True])
@pytest.mark.parametrize("detector,event,pattern", [
    ("tool", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
              "tool_input": {"command": "git status"}}, "tool-detector-*.jsonl"),
    ("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "hello"}, "prompt-detector-*.jsonl"),
    ("fail", {"error": "failed"}, "fails.jsonl"),
])
def test_entrypoints_across_projects_append_to_shared_home(
        runtime, custom_home, detector, event, pattern, monkeypatch, tmp_path):
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("AGENT_RUNTIME")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(HOOK.parents[1]))
    if runtime == "codex":
        monkeypatch.setenv("PLUGIN_ROOT", str(HOOK.parents[1]))
    home_variable = "CODEX_HOME" if runtime == "codex" else "CLAUDE_CONFIG_DIR"
    if custom_home:
        shared_home = tmp_path / runtime
    else:
        monkeypatch.delenv(home_variable)
        shared_home = home / ("." + runtime)
    monkeypatch.setenv("FEEDBACK_LOOP_LOG_PROMPTS", "1")
    if detector == "fail":
        event = {**event, "hook_event_name": "PostToolUse" if runtime == "codex" else "PostToolUseFailure",
                 "tool_response": {"exit_code": 1, "output": "failed"}}

    for project_name in ["project-a", "project-b"]:
        project = tmp_path / project_name
        project.mkdir()
        monkeypatch.setenv("PLUGIN_DATA", str(project / "plugin-data"))
        payload = {**event, "cwd": str(project), "session_id": project_name}
        result = subprocess.run(
            [sys.executable, str(HOOK / (detector + "-detector.py"))],
            input=json.dumps(payload), capture_output=True, text=True, cwd=project)
        assert result.returncode == 0
        assert json.loads(result.stdout) == {}
        assert not result.stderr
        assert not list(project.iterdir())

    [log] = (shared_home / "feedback-loop").glob(pattern)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert [record["session_id"] for record in records] == ["project-a", "project-b"]
    assert all(record["runtime"] == runtime for record in records)
    assert list(tmp_path.rglob("*.jsonl")) == [log]
    assert log.stat().st_mode & 0o077 == 0


def test_failure_retention_preserves_recent_and_unknown(tmp_path):
    directory = tmp_path / "claude/feedback-loop"
    directory.mkdir(parents=True)
    log = directory / "fails.jsonl"
    log.write_text('{"timestamp":"2000-01-01 00:00:00","error":"old"}\nunknown record\n')
    fail.record({"hook_event_name": "PostToolUseFailure", "error": "new"})
    lines = log.read_text().splitlines()
    assert lines[0] == "unknown record"
    assert json.loads(lines[1])["error"] == "new"
    assert len(lines) == 2


def test_prompt_logging_default_preserved(monkeypatch, tmp_path):
    monkeypatch.delenv("FEEDBACK_LOOP_LOG_PROMPTS", raising=False)
    prompt.record({"hook_event_name": "UserPromptSubmit", "prompt": "hello"})
    assert list(tmp_path.rglob("prompt-detector-*.jsonl"))


@pytest.mark.parametrize("detector", ["tool", "prompt", "fail"])
@pytest.mark.parametrize("raw", ["not json", "[]", '{"hook_event_name":"Unrelated"}'])
def test_entrypoints_defer_on_invalid_or_unrelated_input(detector, raw, tmp_path):
    import subprocess
    result = subprocess.run([sys.executable, str(HOOK / (detector + "-detector.py"))], input=raw, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
    assert not list(tmp_path.rglob("*.jsonl"))


@pytest.mark.parametrize("detector,event,pattern", [
    ("tool", {"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"}}, "tool-detector-*.jsonl"),
    ("prompt", {"hook_event_name":"UserPromptSubmit","prompt":"hello"}, "prompt-detector-*.jsonl"),
    ("fail", {"hook_event_name":"PostToolUseFailure","error":"failed"}, "fails.jsonl"),
])
@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_entrypoint_writes_only_its_log(detector, event, pattern, runtime, monkeypatch, tmp_path):
    import subprocess
    monkeypatch.setenv("AGENT_RUNTIME", runtime)
    monkeypatch.setenv("FEEDBACK_LOOP_LOG_PROMPTS", "1")
    result = subprocess.run([sys.executable, str(HOOK / (detector + "-detector.py"))], input=json.dumps(event), capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout) == {}
    directory = tmp_path / runtime / "feedback-loop"
    assert len(list(directory.glob(pattern))) == 1
    assert len(list(directory.glob("*.jsonl"))) == 1


@pytest.mark.parametrize("command,output", [
    ("ls /example/missing", "ls: /example/missing: No such file or directory\n"),
    ("cat /example/private", "cat: /example/private: Permission denied\n"),
    ("/bin/ls /example/missing", "ls: /example/missing: No such file or directory\n"),
])
def test_codex_raw_command_diagnostic(command, output, tmp_path):
    fail.record({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                 "tool_input": {"command": command}, "tool_response": output})
    [log] = tmp_path.rglob("fails.jsonl")
    assert json.loads(log.read_text())["error"] == output.strip()


@pytest.mark.parametrize("command,output", [
    ("echo 'ls: /example/missing: No such file or directory'", "ls: /example/missing: No such file or directory\n"),
    ("ls .", "README.md\nerror.log\n"),
    ("false", ""),
    ("true", ""),
])
def test_raw_output_without_matching_diagnostic_is_not_guessed(command, output, tmp_path):
    fail.record({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                 "tool_input": {"command": command}, "tool_response": output})
    assert not list(tmp_path.rglob("fails.jsonl"))
