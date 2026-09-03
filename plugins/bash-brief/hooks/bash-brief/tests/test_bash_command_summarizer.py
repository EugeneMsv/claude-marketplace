"""Tests for bash-command-summarizer.py hook."""

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

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

# Captured before the autouse _stub_tmux_note/_fixed_now_stamp/_stub_char_budget
# fixtures below ever patch these module attributes, so tests of the real
# implementations don't call the stubs instead.
_REAL_SET_TMUX_WINDOW_NOTE = summarizer.set_tmux_window_note
_REAL_NOW_STAMP = summarizer._now_stamp
_REAL_COMPUTE_SENTENCE_CHAR_BUDGET = summarizer.compute_sentence_char_budget

SAMPLE_SENTENCE = "Parses a JSON file to extract the response status field."


@pytest.fixture(autouse=True)
def _redirect_debug_log(monkeypatch, tmp_path):
    """Keep debug-log writes inside tmp_path instead of the real ~/.claude dir."""
    monkeypatch.setattr(summarizer, "DEBUG_LOG_PATH", tmp_path / "debug.jsonl")


@pytest.fixture(autouse=True)
def _stub_tmux_note(monkeypatch):
    """Prevent run()/main() tests from shelling out to real tmux; spy for assertions."""
    mock = MagicMock()
    monkeypatch.setattr(summarizer, "set_tmux_window_note", mock)
    return mock


FIXED_TIME = "13:45:07"


@pytest.fixture(autouse=True)
def _fixed_now_stamp(monkeypatch):
    """Freeze the message timestamp so assertions can match an exact string."""
    monkeypatch.setattr(summarizer, "_now_stamp", lambda: FIXED_TIME)


FIXED_COLOR = 111


@pytest.fixture(autouse=True)
def _fixed_random_color(monkeypatch):
    """Freeze the tmux note's random color choice for deterministic assertions."""
    monkeypatch.setattr(summarizer.random, "choice", lambda seq: FIXED_COLOR)


@pytest.fixture(autouse=True)
def _stub_char_budget(monkeypatch):
    """Prevent run()/main() tests from shelling out to real tmux for window width."""
    mock = MagicMock(return_value=summarizer.DEFAULT_SENTENCE_BUDGET)
    monkeypatch.setattr(summarizer, "compute_sentence_char_budget", mock)
    return mock


class _StubClient:
    """Fake AnthropicClient instance with a configurable complete() result."""

    def __init__(self, response_text=None, raises=None):
        self.response_text = response_text
        self.raises = raises
        self.received = None

    def complete(self, model, prompt, max_tokens, effort=None):
        self.received = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "effort": effort}
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
            "hook_event_name": "PermissionRequest",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
    )


def _mcp_input(tool_name, tool_input):
    return json.dumps(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": tool_name,
            "tool_input": tool_input,
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

    assert result == {"systemMessage": f"[bash-brief {FIXED_TIME}] {SAMPLE_SENTENCE}"}


def test_run_happyPath_setsTmuxWindowNote(monkeypatch, _stub_tmux_note):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    _stub_tmux_note.assert_called_once_with(f"[bash-brief {FIXED_TIME}]", SAMPLE_SENTENCE)


def test_run_mcpToolHappyPath_returnsSystemMessageAndSetsTmuxNote(monkeypatch, _stub_tmux_note):
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _mcp_input("mcp__trino__execute_query", {"query": "SELECT count(*) FROM orders LIMIT 10"})

    result = summarizer.run(hook_input)

    assert result == {"systemMessage": f"[bash-brief {FIXED_TIME}] {SAMPLE_SENTENCE}"}
    assert "mcp__trino__execute_query" in stub_client.received["prompt"]
    _stub_tmux_note.assert_called_once_with(f"[bash-brief {FIXED_TIME}]", SAMPLE_SENTENCE)


def test_run_noCredentials_doesNotSetTmuxWindowNote(monkeypatch, _stub_tmux_note):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(False))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    _stub_tmux_note.assert_not_called()


def test_run_happyPath_writesAnnotatedDebugLogLine(monkeypatch):
    monkeypatch.setattr(summarizer, "DEBUG_LOG_ENABLED", True)
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    record = json.loads(summarizer.DEBUG_LOG_PATH.read_text().strip())
    assert record["decision"] == "annotated"
    assert record["sentence"] == SAMPLE_SENTENCE
    assert record["subject"] == "cat response.json | jq '.status'"


def test_run_unsupportedTool_writesSkipDebugLogLine(monkeypatch):
    monkeypatch.setattr(summarizer, "DEBUG_LOG_ENABLED", True)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = _bash_input("ls -la", tool_name="Read")

    summarizer.run(hook_input)

    record = json.loads(summarizer.DEBUG_LOG_PATH.read_text().strip())
    assert record["decision"] == "skip_unsupported_tool"
    assert record["tool_name"] == "Read"


def test_run_nonStringToolName_skipsUnsupportedToolWithoutRaising(monkeypatch):
    monkeypatch.setattr(summarizer, "DEBUG_LOG_ENABLED", True)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = json.dumps({"hook_event_name": "PermissionRequest", "tool_name": 123, "tool_input": {}})

    result = summarizer.run(hook_input)

    assert result == {}
    record = json.loads(summarizer.DEBUG_LOG_PATH.read_text().strip())
    assert record["decision"] == "skip_unsupported_tool"
    assert record["tool_name"] == 123


def test_run_debugLogDisabledByDefault_doesNotWriteLogFile(monkeypatch):
    assert summarizer.DEBUG_LOG_ENABLED is False
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = _bash_input("cat response.json | jq '.status'")

    summarizer.run(hook_input)

    assert not summarizer.DEBUG_LOG_PATH.exists()


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


def test_nowStamp_returns24HourTimeNoDate():
    assert re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d:[0-5]\d", _REAL_NOW_STAMP())


def test_resolveModel_envVarUnset_usesUndatedAlias():
    assert summarizer.resolve_model({}) == "claude-haiku-4-5"


def test_computeSentenceCharBudget_noTmuxPane_returnsDefaultBudget():
    assert _REAL_COMPUTE_SENTENCE_CHAR_BUDGET("[prefix]", env={}) == summarizer.DEFAULT_SENTENCE_BUDGET


def test_computeSentenceCharBudget_withTmuxPane_computesFromWindowWidth(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout="100\n"),
    )

    budget = _REAL_COMPUTE_SENTENCE_CHAR_BUDGET("[prefix]", env={"TMUX_PANE": "%7"})

    expected = (100 - summarizer.TMUX_ROW_PADDING) * 2 - len("[prefix]") - 1
    assert budget == expected


def test_computeSentenceCharBudget_tmuxFails_returnsDefaultBudget(monkeypatch):
    def _fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    budget = _REAL_COMPUTE_SENTENCE_CHAR_BUDGET("[prefix]", env={"TMUX_PANE": "%7"})

    assert budget == summarizer.DEFAULT_SENTENCE_BUDGET


def test_computeSentenceCharBudget_nonIntegerWidth_returnsDefaultBudget(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout="not-a-number\n"),
    )

    budget = _REAL_COMPUTE_SENTENCE_CHAR_BUDGET("[prefix]", env={"TMUX_PANE": "%7"})

    assert budget == summarizer.DEFAULT_SENTENCE_BUDGET


def test_computeSentenceCharBudget_tinyWindow_neverGoesBelowQuarterDefault(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout="5\n"),
    )

    budget = _REAL_COMPUTE_SENTENCE_CHAR_BUDGET("[a much longer prefix than the window]", env={"TMUX_PANE": "%7"})

    assert budget == summarizer.DEFAULT_SENTENCE_BUDGET // 4


def test_summarizeCommand_sendsCharLimitInPrompt():
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)

    summarizer.summarize_command(stub_client, "ls -la", 42)

    assert "42" in stub_client.received["prompt"]


def test_summarizeCommand_omitsEffort():
    """Haiku 4.5 (the default model here) has no output_config.effort support -
    the API rejects it with HTTP 400 - so this call site must pass None."""
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)

    summarizer.summarize_command(stub_client, "ls -la", 42)

    assert stub_client.received["effort"] is None


def test_buildMcpSubject_emptyParams_rendersEmptyJsonObject():
    subject = summarizer.build_mcp_subject("mcp__trino__list_catalogs", {})

    assert subject == "MCP tool `mcp__trino__list_catalogs` invoked with parameters: {}"


def test_buildMcpSubject_typicalParams_rendersToolNameAndJson():
    tool_input = {"query": "SELECT count(*) FROM orders LIMIT 10", "catalog": "hive"}

    subject = summarizer.build_mcp_subject("mcp__trino__execute_query", tool_input)

    assert subject.startswith("MCP tool `mcp__trino__execute_query` invoked with parameters: ")
    assert json.loads(subject.split("parameters: ", 1)[1]) == tool_input


def test_buildMcpSubject_oversizedParams_truncatesToMaxChars():
    tool_input = {"body": "x" * (summarizer.MAX_MCP_PARAMS_CHARS * 2)}

    subject = summarizer.build_mcp_subject("mcp__slack__slack_send_message", tool_input)

    params_text = subject.split("parameters: ", 1)[1]
    assert len(params_text) == summarizer.MAX_MCP_PARAMS_CHARS


def test_summarizeCommand_mcpSubjectWithBraces_doesNotRaiseAndIncludesSubject():
    stub_client = _StubClient(response_text=SAMPLE_SENTENCE)
    subject = summarizer.build_mcp_subject("mcp__trino__execute_query", {"query": "SELECT 1"})

    summarizer.summarize_command(stub_client, subject, 100)

    assert subject in stub_client.received["prompt"]


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
    assert summarizer.clean_sentence(raw, summarizer.MAX_SENTENCE_CHARS) == expected


def test_cleanSentence_emptyResponse_returnsEmptyString():
    assert summarizer.clean_sentence("   \n  ", summarizer.MAX_SENTENCE_CHARS) == ""


def test_cleanSentence_noTrailingPunctuation_appendsPeriod():
    assert summarizer.clean_sentence(
        "Lists files in the current directory", summarizer.MAX_SENTENCE_CHARS
    ) == ("Lists files in the current directory.")


def test_cleanSentence_overLength_truncatesWithEllipsisWithinBound():
    long_sentence = "Runs a command that does something. " * 20

    result = summarizer.clean_sentence(long_sentence, summarizer.MAX_SENTENCE_CHARS)

    assert len(result) <= summarizer.MAX_SENTENCE_CHARS + 1
    assert result.endswith("…")


def test_cleanSentence_charLimitSmallerThanMax_truncatesToCharLimit():
    long_sentence = "Runs a command that does something. " * 20

    result = summarizer.clean_sentence(long_sentence, 40)

    assert len(result) <= 41
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
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "cat response.json | jq '.status'"},
    }

    result = _run_main(hook_input, monkeypatch, capsys)

    assert result == {"systemMessage": f"[bash-brief {FIXED_TIME}] {SAMPLE_SENTENCE}"}


def test_main_toolNameNotBash_writesEmptyDict(monkeypatch, capsys):
    monkeypatch.setattr(summarizer, "AnthropicClient", _stub_anthropic_client(True))
    hook_input = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/foo"},
    }

    result = _run_main(hook_input, monkeypatch, capsys)

    assert result == {}


def test_tmuxNoteColors_hasAtLeast20DistinctValidColors():
    assert len(summarizer.TMUX_NOTE_COLORS) >= 20
    assert len(set(summarizer.TMUX_NOTE_COLORS)) == len(summarizer.TMUX_NOTE_COLORS)
    assert all(0 <= c <= 255 for c in summarizer.TMUX_NOTE_COLORS)


def test_setTmuxWindowNote_noTmuxPane_doesNotCallSubprocess(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called without $TMUX_PANE")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "test note", env={})


def test_setTmuxWindowNote_withTmuxPane_resolvesWindowThenSetsBothLineOptions(monkeypatch):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="@3\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    colored_prefix = f"#[fg=colour{FIXED_COLOR}][prefix]#[fg=colour{summarizer.TMUX_NOTE_BASE_COLOR}]"
    expected_line1, expected_line2 = summarizer.split_into_two_lines(f"{colored_prefix} some sentence")

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "some sentence", env={"TMUX_PANE": "%7"})

    assert calls[0] == ["tmux", "display-message", "-p", "-t", "%7", "#{window_id}"]
    assert calls[1] == ["tmux", "set-option", "-w", "-t", "@3", "@bash_brief_note_1", expected_line1]
    assert calls[2] == ["tmux", "set-option", "-w", "-t", "@3", "@bash_brief_note_2", expected_line2]


def test_setTmuxWindowNote_coloring_onlyWrapsPrefixNotSentence(monkeypatch):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["tmux", "display-message"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="@3\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "some sentence", env={"TMUX_PANE": "%7"})

    combined = calls[1][-1] + " " + calls[2][-1]
    reset = f"#[fg=colour{summarizer.TMUX_NOTE_BASE_COLOR}]"
    assert f"#[fg=colour{FIXED_COLOR}][prefix]{reset}" in combined
    assert "some sentence" in combined
    # No further color-open codes after the reset - the sentence stays in the row's base color.
    assert combined.split(reset, 1)[1].count("#[fg=colour") == 0


def test_setTmuxWindowNote_emptyWindowId_doesNotCallSetOption(monkeypatch):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="   \n")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "some sentence", env={"TMUX_PANE": "%7"})

    assert len(calls) == 1


def test_setTmuxWindowNote_displayMessageFails_doesNotRaise(monkeypatch):
    def _fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "some sentence", env={"TMUX_PANE": "%7"})


def test_setTmuxWindowNote_tmuxBinaryMissing_doesNotRaise(monkeypatch):
    def _fake_run(args, **kwargs):
        raise FileNotFoundError("tmux not found")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _REAL_SET_TMUX_WINDOW_NOTE("[prefix]", "some sentence", env={"TMUX_PANE": "%7"})


def test_splitIntoTwoLines_emptyString_returnsTwoEmptyStrings():
    assert summarizer.split_into_two_lines("") == ("", "")


def test_splitIntoTwoLines_twoWords_splitsAtTheSpace():
    assert summarizer.split_into_two_lines("left right") == ("left", "right")


def test_splitIntoTwoLines_noSpaces_keepsWholeWordOnFirstLine():
    assert summarizer.split_into_two_lines("abcdefgh") == ("abcdefgh", "")


def test_splitIntoTwoLines_longSentence_preservesAllWordsInOrder():
    text = "🔎 [bash-brief] Executes a Python one-liner that prints a debug message."

    line1, line2 = summarizer.split_into_two_lines(text)

    assert line1
    assert line2
    assert (line1 + " " + line2).split() == text.split()


def test_splitIntoTwoLines_defaultRatio_firstLineLongerThanSecond():
    text = " ".join(["word"] * 10)

    line1, line2 = summarizer.split_into_two_lines(text)

    assert len(line1) > len(line2)


def test_splitIntoTwoLines_customRatio_biasesTowardRequestedShare():
    text = " ".join(["word"] * 10)

    even_line1, _ = summarizer.split_into_two_lines(text, first_ratio=0.5)
    biased_line1, _ = summarizer.split_into_two_lines(text, first_ratio=summarizer.TMUX_NOTE_FIRST_LINE_RATIO)

    assert len(biased_line1) > len(even_line1)
