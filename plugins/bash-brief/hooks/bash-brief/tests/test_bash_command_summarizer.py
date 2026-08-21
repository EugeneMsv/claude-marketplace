"""Tests for bash-command-summarizer.py hook."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))


def _load_hook_module():
    """Load bash-command-summarizer.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / "bash-command-summarizer.py"
    spec = importlib.util.spec_from_file_location("bash_command_summarizer", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summarizer = _load_hook_module()

SAMPLE_SENTENCE = "Parses a JSON file to extract the response status field."


@pytest.fixture(autouse=True)
def _redirect_debug_log(monkeypatch, tmp_path):
    """Keep debug-log writes inside tmp_path instead of the real ~/.claude dir."""
    monkeypatch.setattr(summarizer, "DEBUG_LOG_PATH", tmp_path / "debug.jsonl")


class _StubClient:
    """Fake AnthropicClient instance with a configurable complete() result."""

    def __init__(self, response_text=None, raises=None):
        self.response_text = response_text
        self.raises = raises
        self.received = None

    def complete(self, model, prompt, max_tokens):
        self.received = {"model": model, "prompt": prompt, "max_tokens": max_tokens}
        if self.raises is not None:
            raise self.raises
        return self.response_text


def _stub_anthropic_client(has_credentials, client_instance=None):
    """Build a stand-in AnthropicClient class with static has_credentials/from_env."""

    class Stub:
        @staticmethod
        def has_credentials():
            return has_credentials

        @staticmethod
        def from_env():
            return client_instance

    return Stub


def _bash_input(command, tool_name="Bash"):
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
    )


def test_run_toolNameNotBash_returnsEmpty(monkeypatch):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = _bash_input("ls -la", tool_name="Read")

    result = summarizer.run(hook_input)

    assert result == {}


def test_run_emptyCommand_returnsEmpty(monkeypatch):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = _bash_input("   ")

    result = summarizer.run(hook_input)

    assert result == {}


def test_run_malformedJson_returnsEmpty(monkeypatch):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))

    result = summarizer.run("{not valid json")

    assert result == {}


def test_run_noCredentials_returnsEmpty(monkeypatch):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(False))
    hook_input = _bash_input("cat response.json | jq '.status'")

    result = summarizer.run(hook_input)

    assert result == {}


def test_run_llmRaises_returnsEmpty(monkeypatch):
    stub_client = _StubClient(raises=RuntimeError("boom"))
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    result = summarizer.run(hook_input)

    assert result == {}


def test_run_happyPath_returnsSystemMessageWithSentence(monkeypatch):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    result = summarizer.run(hook_input)

    assert result == {"systemMessage": f"[bash-brief] {SAMPLE_SENTENCE}"}


def test_run_happyPath_writesAnnotatedDebugLogLine(monkeypatch):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    record = json.loads(summarizer.DEBUG_LOG_PATH.read_text().strip())
    assert record["decision"] == "annotated"
    assert record["sentence"] == SAMPLE_SENTENCE
    assert record["command"] == "cat response.json | jq '.status'"


def test_run_toolNameNotBash_writesSkipDebugLogLine(monkeypatch):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = _bash_input("ls -la", tool_name="Read")

    summarizer.run(hook_input)

    record = json.loads(summarizer.DEBUG_LOG_PATH.read_text().strip())
    assert record["decision"] == "skip_not_bash"
    assert record["tool_name"] == "Read"


def test_run_happyPath_sendsCommandInPrompt(monkeypatch):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    assert "cat response.json | jq '.status'" in stub_client.received["prompt"]


def test_run_emptyModelResponse_returnsEmpty(monkeypatch):
    stub_client = _StubClient(response_text="   ")
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("ls -la")

    result = summarizer.run(hook_input)

    assert result == {}


def test_resolveModel_envVarSet_usesEnvValue():
    env = {"ANTHROPIC_DEFAULT_HAIKU_MODEL": "us.anthropic.claude-haiku-4-5-20251001-v1:0"}

    assert summarizer.resolve_model(env) == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_resolveModel_envVarUnset_usesUndatedAlias():
    assert summarizer.resolve_model({}) == "claude-haiku-4-5"


@pytest.mark.parametrize(
    "raw, expected",
    [
        (SAMPLE_SENTENCE, SAMPLE_SENTENCE),
        (f'"{SAMPLE_SENTENCE}"', SAMPLE_SENTENCE),
        (f"{SAMPLE_SENTENCE}\nSome extra trailing line the model shouldn't add.", SAMPLE_SENTENCE),
        (f"- {SAMPLE_SENTENCE}", SAMPLE_SENTENCE),
        (f"1. {SAMPLE_SENTENCE}", SAMPLE_SENTENCE),
    ],
)
def test_cleanSentence_variousRawShapes_reducesToSingleCleanSentence(raw, expected):
    assert summarizer.clean_sentence(raw) == expected


def test_cleanSentence_emptyResponse_returnsEmptyString():
    assert summarizer.clean_sentence("   \n  ") == ""


def test_cleanSentence_noTrailingPunctuation_appendsPeriod():
    assert summarizer.clean_sentence("Lists files in the current directory") == (
        "Lists files in the current directory."
    )


def test_cleanSentence_overLength_truncatesWithEllipsisWithinBound():
    long_sentence = "Runs a command that does something. " * 20

    result = summarizer.clean_sentence(long_sentence)

    assert len(result) <= summarizer.MAX_SENTENCE_CHARS + 1
    assert result.endswith("…")


def _run_main(hook_input: dict, monkeypatch, capsys) -> dict:
    stdin = io.StringIO(json.dumps(hook_input))
    monkeypatch.setattr(sys, "stdin", stdin)
    summarizer.main()
    return json.loads(capsys.readouterr().out)


def test_main_happyPath_writesSystemMessageJsonToStdout(monkeypatch, capsys):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat response.json | jq '.status'"},
    }

    result = _run_main(hook_input, monkeypatch, capsys)

    assert result == {"systemMessage": f"[bash-brief] {SAMPLE_SENTENCE}"}


def test_main_toolNameNotBash_writesEmptyDict(monkeypatch, capsys):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/foo"},
    }

    result = _run_main(hook_input, monkeypatch, capsys)

    assert result == {}
