"""Tests for security-judge.py hook."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))


def _load_hook_module():
    """Load security-judge.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / "security-judge.py"
    spec = importlib.util.spec_from_file_location("security_judge", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


judge = _load_hook_module()


@pytest.fixture(autouse=True)
def _redirect_log(monkeypatch, tmp_path):
    """Keep decision-log writes inside tmp_path instead of the real ~/.claude dir."""
    monkeypatch.setattr(judge, "LOG_PATH", tmp_path / "decisions.jsonl")


def _log_lines():
    if not judge.LOG_PATH.exists():
        return []
    return [json.loads(line) for line in judge.LOG_PATH.read_text().splitlines() if line]


# --- _log ---------------------------------------------------------------------


def test_log_decidedRecord_ordersFieldsTimestampOutcomeDecisionReasoningCommandThenRest():
    judge._log(
        {
            "session_id": "sess-1",
            "cwd": "/tmp/project",
            "command": "python3 -c 'print(1)'",
            "outcome": "decided",
            "decision": "allow",
            "reasoning": "pure computation",
        }
    )

    [record] = _log_lines()
    assert list(record.keys()) == [
        "timestamp",
        "outcome",
        "decision",
        "reasoning",
        "command",
        "session_id",
        "cwd",
    ]


def test_log_decidedRecordWithElapsedMs_ordersElapsedMsBeforeReasoning():
    judge._log(
        {
            "session_id": "sess-1",
            "command": "python3 -c 'print(1)'",
            "outcome": "decided",
            "decision": "allow",
            "elapsed_ms": 842,
            "reasoning": "pure computation",
        }
    )

    [record] = _log_lines()
    assert list(record.keys()) == [
        "timestamp",
        "outcome",
        "decision",
        "elapsed_ms",
        "reasoning",
        "command",
        "session_id",
    ]


def test_log_skipRecord_omitsMissingFieldsButKeepsOrderOfPresentOnes():
    judge._log({"session_id": "sess-1", "cwd": "/tmp/project", "outcome": "skip_unwatched_command"})

    [record] = _log_lines()
    assert list(record.keys()) == ["timestamp", "outcome", "session_id", "cwd"]


def test_log_errorRecord_errorFieldFollowsCommandFieldsAsPartOfRest():
    judge._log({"session_id": None, "command": None, "cwd": None, "outcome": "error", "error": "malformed_json"})

    [record] = _log_lines()
    assert list(record.keys()) == ["timestamp", "outcome", "command", "session_id", "cwd", "error"]


# --- resolve_model -----------------------------------------------------------


def test_resolveModel_envVarSet_usesEnvValue():
    env = {"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6"}

    assert judge.resolve_model(env) == "claude-sonnet-4-6"


def test_resolveModel_envVarUnset_usesDefault():
    assert judge.resolve_model({}) == "claude-sonnet-5"


# --- resolve_effort ------------------------------------------------------------


def test_resolveEffort_envVarUnset_defaultsToMedium():
    """Balances latency (this hook blocks the permission dialog) against
    classification depth on adversarial/obfuscated commands."""
    assert judge.resolve_effort({}) == "medium"


@pytest.mark.parametrize("level", ["max", "xhigh", "high", "medium", "low"])
def test_resolveEffort_envVarSetToValidLevel_usesEnvValue(level):
    assert judge.resolve_effort({judge.EFFORT_ENV_VAR: level}) == level


def test_resolveEffort_envVarSetToInvalidValue_fallsBackToMedium():
    assert judge.resolve_effort({judge.EFFORT_ENV_VAR: "extreme"}) == "medium"


# --- resolve_watched_patterns -------------------------------------------------


def test_resolveWatchedPatterns_unset_defaultsToPython3():
    assert judge.resolve_watched_patterns({}) == ("python3*",)


def test_resolveWatchedPatterns_emptyString_coversNothing():
    assert judge.resolve_watched_patterns({judge.WATCHED_COMMANDS_ENV_VAR: ""}) == ()


def test_resolveWatchedPatterns_commaSeparatedList_parsesEachEntry():
    env = {judge.WATCHED_COMMANDS_ENV_VAR: "python3, git push , npm install"}

    assert judge.resolve_watched_patterns(env) == ("python3*", "git push*", "npm install*")


def test_resolveWatchedPatterns_entryWithExplicitStar_usedAsIs():
    env = {judge.WATCHED_COMMANDS_ENV_VAR: "python3 -m *"}

    assert judge.resolve_watched_patterns(env) == ("python3 -m *",)


# --- segment_commands ---------------------------------------------------------


def test_segmentCommands_plainCommand_returnsSingleSegment():
    assert judge.segment_commands("python3 -c 'print(1)'") == ["python3 -c print(1)"]


def test_segmentCommands_pipedCommand_returnsTwoSegments():
    assert judge.segment_commands("cat data.json | python3 -") == ["cat data.json", "python3 -"]


def test_segmentCommands_chainedCommand_returnsTwoSegments():
    assert judge.segment_commands("build.sh && python3 test.py") == ["build.sh", "python3 test.py"]


def test_segmentCommands_sudoPrefixed_skipsWrapperToken():
    assert judge.segment_commands("sudo python3 x.py") == ["python3 x.py"]


def test_segmentCommands_envAssignmentPrefixed_skipsAssignmentToken():
    assert judge.segment_commands("FOO=bar python3 x.py") == ["python3 x.py"]


def test_segmentCommands_quotedPipeInArgument_notTreatedAsBoundary():
    assert judge.segment_commands("python3 -c \"print('a|b')\"") == ["python3 -c print('a|b')"]


def test_segmentCommands_unbalancedQuote_fallsBackToWholeString():
    assert judge.segment_commands('python3 -c "unterminated') == ['python3 -c "unterminated']


def test_segmentCommands_emptyCommand_returnsEmptyList():
    assert judge.segment_commands("") == []


# --- is_watched_command --------------------------------------------------------


def test_isWatchedCommand_matchesSecondSegment_returnsTrue():
    assert judge.is_watched_command("cat data.json | python3 -", ("python3*",)) is True


def test_isWatchedCommand_noPatterns_returnsFalse():
    assert judge.is_watched_command("python3 x.py", ()) is False


def test_isWatchedCommand_trailingFlagsOnDefaultPrefix_matches():
    assert judge.is_watched_command("python3 -m http.server 8000", ("python3*",)) is True


def test_isWatchedCommand_noSegmentMatches_returnsFalse():
    assert judge.is_watched_command("ls -la", ("python3*",)) is False


# --- resolve_segmenter ---------------------------------------------------------


def test_resolveSegmenter_unset_defaultsToShlex():
    assert judge.resolve_segmenter({}) == "shlex"


def test_resolveSegmenter_explicitShlex_usesShlex():
    assert judge.resolve_segmenter({judge.SEGMENTER_ENV_VAR: "shlex"}) == "shlex"


def test_resolveSegmenter_explicitBashlex_usesBashlex():
    assert judge.resolve_segmenter({judge.SEGMENTER_ENV_VAR: "bashlex"}) == "bashlex"


def test_resolveSegmenter_invalidValue_fallsBackToShlex():
    assert judge.resolve_segmenter({judge.SEGMENTER_ENV_VAR: "regex"}) == "shlex"


# --- segment_commands_bashlex ---------------------------------------------------

try:
    import bashlex as _bashlex_module  # noqa: F401

    _HAS_BASHLEX = True
except ImportError:
    _HAS_BASHLEX = False

requires_bashlex = pytest.mark.skipif(not _HAS_BASHLEX, reason="prototype segmenter is opt-in")

# The exact script from the conversation that motivated this prototype: a
# `for ...; do ... done` loop whose body pipes a grep through && and ||.
# Under segment_commands() (flat punctuation-token split), the loop body
# segments as ["do echo ... grep ... $f", "echo ... REVIEW", "echo ... clean: ..."]
# - "do" is the head token (not in LEADING_WRAPPER_TOKENS, so never stripped),
# so a "grep*" pattern never matches. segment_commands_bashlex() walks into
# the for-loop's body instead and yields "grep ..." as its own segment.
FOR_LOOP_GREP_SCRIPT = """\
cd /home/user/dev/repo/myrepo
echo "=== machine-neutrality sweep ==="
for f in a.md b.md; do
  echo "-- $f"
  grep -nE 'pattern' "$f" && echo "   ^ REVIEW" || echo "   clean"
done
"""


@requires_bashlex
def test_segmentCommandsBashlex_plainCommand_returnsSingleSegment():
    assert judge.segment_commands_bashlex("python3 -c 'print(1)'") == ["python3 -c print(1)"]


@requires_bashlex
def test_segmentCommandsBashlex_pipedCommand_returnsTwoSegments():
    assert judge.segment_commands_bashlex("cat data.json | python3 -") == ["cat data.json", "python3 -"]


@requires_bashlex
def test_segmentCommandsBashlex_chainedCommand_returnsTwoSegments():
    assert judge.segment_commands_bashlex("build.sh && python3 test.py") == ["build.sh", "python3 test.py"]


@requires_bashlex
def test_segmentCommandsBashlex_sudoPrefixed_skipsWrapperToken():
    assert judge.segment_commands_bashlex("sudo python3 x.py") == ["python3 x.py"]


@requires_bashlex
def test_segmentCommandsBashlex_envAssignmentPrefixed_skipsAssignmentToken():
    assert judge.segment_commands_bashlex("FOO=bar python3 x.py") == ["python3 x.py"]


@requires_bashlex
def test_segmentCommandsBashlex_malformedBash_raises():
    with pytest.raises(Exception):
        judge.segment_commands_bashlex("if grep x; then")


@requires_bashlex
def test_segmentCommandsBashlex_forLoopBody_findsGrepAsOwnSegment():
    segments = judge.segment_commands_bashlex(FOR_LOOP_GREP_SCRIPT)

    assert "grep -nE pattern $f" in segments


@requires_bashlex
def test_segmentCommandsBashlex_ifStatementBody_findsCommandAsOwnSegment():
    segments = judge.segment_commands_bashlex("if grep -q x file; then echo yes; fi")

    assert "grep -q x file" in segments


@requires_bashlex
def test_segmentCommandsBashlex_subshell_findsCommandAsOwnSegment():
    segments = judge.segment_commands_bashlex("( cd /tmp && grep foo x )")

    assert "grep foo x" in segments


@requires_bashlex
def test_segmentCommandsBashlex_commandSubstitution_findsInnerCommandAsOwnSegment():
    segments = judge.segment_commands_bashlex("echo $(grep foo bar.txt)")

    assert "grep foo bar.txt" in segments


# The exact shape that triggered the "delimited by end-of-file" ParsingError:
# a heredoc whose opener quotes its delimiter (<<'PY') to suppress
# $-expansion inside the body - the standard idiom for embedded scripts, and
# what a "cd ...\npython3 - <<'PY' ... PY" invocation uses. Without
# _unquote_heredoc_delimiters(), bashlex.parse() never finds the closing
# "PY" line here even though one is present.
HEREDOC_QUOTED_DELIM_SCRIPT = """\
cd /home/user/dev/repo/myrepo
python3 - <<'PY'
import pathlib
grep_like = pathlib.Path("x").read_text()
PY
"""


@requires_bashlex
def test_segmentCommandsBashlex_quotedHeredocDelimiter_doesNotRaise():
    segments = judge.segment_commands_bashlex(HEREDOC_QUOTED_DELIM_SCRIPT)

    assert any(segment.startswith("python3") for segment in segments)


@requires_bashlex
def test_segmentCommandsBashlex_doubleQuotedHeredocDelimiter_doesNotRaise():
    segments = judge.segment_commands_bashlex('python3 - <<"PY"\nprint(1)\nPY\n')

    assert segments == ["python3 -"]


@requires_bashlex
def test_segmentCommandsBashlex_dashQuotedHeredocDelimiter_doesNotRaise():
    segments = judge.segment_commands_bashlex("python3 - <<-'PY'\n\tprint(1)\n\tPY\n")

    assert segments == ["python3 -"]


@requires_bashlex
def test_segmentCommandsBashlex_unquotedHeredocDelimiter_stillWorks():
    segments = judge.segment_commands_bashlex("python3 - <<PY\nprint(1)\nPY\n")

    assert segments == ["python3 -"]


@requires_bashlex
def test_segmentCommandsBashlex_hereStringNotMistakenForHeredoc():
    """<<< is a herestring (no delimiter word) - the quoted-heredoc rewrite
    must not touch it via a partial match on its leading <<."""
    segments = judge.segment_commands_bashlex("python3 -c 'x' <<< 'input data'")

    assert segments == ["python3 -c x"]


# --- is_watched_command: shlex vs bashlex on the motivating script -------------


def test_isWatchedCommand_forLoopGrepScript_shlexSegmenter_missesGrep():
    """Documents the false negative this prototype exists to fix."""
    env = {judge.SEGMENTER_ENV_VAR: "shlex"}

    assert judge.is_watched_command(FOR_LOOP_GREP_SCRIPT, ("grep*",), env) is False


@requires_bashlex
def test_isWatchedCommand_forLoopGrepScript_bashlexSegmenter_catchesGrep():
    env = {judge.SEGMENTER_ENV_VAR: "bashlex"}

    assert judge.is_watched_command(FOR_LOOP_GREP_SCRIPT, ("grep*",), env) is True


def test_isWatchedCommand_heredocQuotedDelimiterScript_shlexSegmenter_missesPython3():
    """Documents the false negative this fix exists to close: shlex merges
    the newline-separated "cd ..." and "python3 - <<'PY'" into one segment
    headed by "cd", so "python3*" never matches."""
    env = {judge.SEGMENTER_ENV_VAR: "shlex"}

    assert judge.is_watched_command(HEREDOC_QUOTED_DELIM_SCRIPT, ("python3*",), env) is False


@requires_bashlex
def test_isWatchedCommand_heredocQuotedDelimiterScript_bashlexSegmenter_catchesPython3():
    env = {judge.SEGMENTER_ENV_VAR: "bashlex"}

    assert judge.is_watched_command(HEREDOC_QUOTED_DELIM_SCRIPT, ("python3*",), env) is True


def test_isWatchedCommand_bashlexSegmenterButNotInstalled_fallsBackToShlexResult():
    env = {judge.SEGMENTER_ENV_VAR: "bashlex"}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "bashlex", None)

        result = judge.is_watched_command(FOR_LOOP_GREP_SCRIPT, ("grep*",), env)

    assert result is False  # same as the shlex segmenter would give directly


# --- load_reference_bash_rules --------------------------------------------------


def test_loadReferenceBashRules_missingFile_returnsEmptyLists(tmp_path):
    result = judge.load_reference_bash_rules(tmp_path / "does-not-exist.json")

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceBashRules_malformedJson_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json")

    result = judge.load_reference_bash_rules(settings_path)

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceBashRules_mixedBashAndNonBashEntries_filtersToOnlyBash(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(git status)", "Edit(*.py)"],
                    "ask": ["Bash(git push *)", "mcp__foo__bar"],
                    "deny": ["Bash(rm -rf *)"],
                }
            }
        )
    )

    result = judge.load_reference_bash_rules(settings_path)

    assert result == {
        "allow": ["Bash(git status)"],
        "ask": ["Bash(git push *)"],
        "deny": ["Bash(rm -rf *)"],
    }


def test_loadReferenceBashRules_emptyPermissionLists_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"permissions": {"allow": [], "ask": [], "deny": []}}))

    result = judge.load_reference_bash_rules(settings_path)

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceBashRules_noPermissionsKey_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"someOtherKey": True}))

    result = judge.load_reference_bash_rules(settings_path)

    assert result == {"allow": [], "ask": [], "deny": []}


# --- load_auto_mode_context ------------------------------------------------------

_EMPTY_AUTO_MODE = {"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}


def test_loadAutoModeContext_missingFile_returnsEmptyLists(tmp_path):
    result = judge.load_auto_mode_context(tmp_path / "does-not-exist.json")

    assert result == _EMPTY_AUTO_MODE


def test_loadAutoModeContext_malformedJson_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json")

    result = judge.load_auto_mode_context(settings_path)

    assert result == _EMPTY_AUTO_MODE


def test_loadAutoModeContext_noAutoModeKey_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"someOtherKey": True}))

    result = judge.load_auto_mode_context(settings_path)

    assert result == _EMPTY_AUTO_MODE


def test_loadAutoModeContext_populatedSections_returnsEachList(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "autoMode": {
                    "environment": ["Org: Acme Corp"],
                    "allow": ["Read-only shell inspection is allowed"],
                    "soft_deny": ["Never run prod ops without asking"],
                    "hard_deny": ["Never modify prod without asking"],
                }
            }
        )
    )

    result = judge.load_auto_mode_context(settings_path)

    assert result == {
        "environment": ["Org: Acme Corp"],
        "allow": ["Read-only shell inspection is allowed"],
        "soft_deny": ["Never run prod ops without asking"],
        "hard_deny": ["Never modify prod without asking"],
    }


def test_loadAutoModeContext_defaultsPlaceholder_filteredOut(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "autoMode": {
                    "hard_deny": ["$defaults", "Never modify prod without asking"],
                }
            }
        )
    )

    result = judge.load_auto_mode_context(settings_path)

    assert result["hard_deny"] == ["Never modify prod without asking"]


# --- run() integration ---------------------------------------------------------


class _StubClient:
    """Fake AnthropicClient instance with a configurable complete_with_tool() result."""

    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.received = None

    def complete_with_tool(
        self, model, prompt, tool_name, tool_description, input_schema, max_tokens,
        effort=None, system=None, cache_system=False,
    ):
        self.received = {
            "model": model,
            "prompt": prompt,
            "tool_name": tool_name,
            "tool_description": tool_description,
            "input_schema": input_schema,
            "max_tokens": max_tokens,
            "effort": effort,
            "system": system,
            "cache_system": cache_system,
        }
        if self.raises is not None:
            raise self.raises
        return self.result


def _stub_anthropic_client(has_credentials, client_instance=None):
    """Build a stand-in AnthropicClient class with static has_credentials/from_env."""

    class Stub:
        @staticmethod
        def has_credentials():
            return has_credentials

        @staticmethod
        def from_env(timeout=None):
            return client_instance

    return Stub


def _hook_input(command, tool_name="Bash", session_id="sess-1", cwd="/tmp/project"):
    return json.dumps(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "session_id": session_id,
            "cwd": cwd,
        }
    )


@pytest.fixture(autouse=True)
def _redirect_settings_path(monkeypatch, tmp_path):
    """Reference-rules loading is covered by its own dedicated tests above -
    point run()'s no-arg call at a non-existent settings.json (resolves to
    empty rule lists, per load_reference_bash_rules' own missing-file
    behavior) so run() tests don't depend on the real environment's file."""
    monkeypatch.setattr(judge, "SETTINGS_PATH", tmp_path / "does-not-exist-settings.json")


def test_run_allowDecision_returnsAllowBehaviorAndLogsDecided(monkeypatch):
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "pure computation"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow", "message": "pure computation"},
        }
    }
    [record] = _log_lines()
    assert record["outcome"] == "decided"
    assert record["decision"] == "allow"
    assert isinstance(record["elapsed_ms"], int)
    assert record["elapsed_ms"] >= 0


def test_run_watchedCommand_logsCommandUpToMaxCommandCharsNotJustFirst500(monkeypatch):
    long_command = "python3 -c \"print('" + ("x" * 600) + "')\""
    assert 500 < len(long_command) <= judge.MAX_COMMAND_CHARS
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "pure computation"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input(long_command))

    [record] = _log_lines()
    assert record["command"] == long_command


def test_run_askDecision_returnsAskBehaviorWithMessage(monkeypatch):
    stub_client = _StubClient(result={"decision": "ask", "reasoning": "opens a local listener"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -m http.server 8000"))

    assert result["hookSpecificOutput"]["decision"] == {
        "behavior": "ask",
        "message": "opens a local listener",
    }


def test_run_denyDecision_returnsDenyBehaviorWithMessage(monkeypatch):
    stub_client = _StubClient(result={"decision": "deny", "reasoning": "deletes filesystem root"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c \"import shutil; shutil.rmtree('/')\""))

    assert result["hookSpecificOutput"]["decision"] == {
        "behavior": "deny",
        "message": "deletes filesystem root",
    }


def test_run_malformedJson_returnsEmptyAndLogsError(monkeypatch):
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))

    result = judge.run("{not valid json")

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "error"
    assert record["error"] == "malformed_json"


def test_run_defaultEnv_passesMediumEffortToCompleteWithTool(monkeypatch):
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "pure computation"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 -c 'print(1)'"))

    assert stub_client.received["effort"] == "medium"


def test_run_effortEnvVarSet_passesConfiguredEffort(monkeypatch):
    monkeypatch.setenv(judge.EFFORT_ENV_VAR, "high")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "pure computation"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 -c 'print(1)'"))

    assert stub_client.received["effort"] == "high"


def test_run_nonBashTool_returnsEmptyAndLogsSkipUnsupportedTool(monkeypatch):
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))

    result = judge.run(_hook_input("ls -la", tool_name="Read"))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_unsupported_tool"


def test_run_emptyCommand_returnsEmptyAndLogsSkipEmptyCommand(monkeypatch):
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))

    result = judge.run(_hook_input("   "))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_empty_command"


def test_run_unwatchedCommand_returnsEmptyAndLogsSkipUnwatchedCommand(monkeypatch):
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))
    monkeypatch.delenv(judge.WATCHED_COMMANDS_ENV_VAR, raising=False)

    result = judge.run(_hook_input("ls -la"))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_unwatched_command"


def test_run_noCredentials_returnsEmptyAndLogsSkipNoCredentials(monkeypatch):
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(False))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_no_credentials"


def test_run_llmRaises_returnsEmptyAndLogsError(monkeypatch):
    stub_client = _StubClient(raises=RuntimeError("boom"))
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "error"
    assert "boom" in record["error"]


def test_run_invalidDecisionValue_returnsEmptyAndLogsError(monkeypatch):
    stub_client = _StubClient(result={"decision": "maybe", "reasoning": "unsure"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "error"
    assert "maybe" in record["error"]


def test_run_watchedCommand_sendsCommandAndCwdInUserPromptNotSystem(monkeypatch):
    """cwd/command are the per-call variable part - they belong in the user
    message, never in the cacheable system block."""
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 sync_inventory_ledger.py", cwd="/Users/dev/project"))

    assert "python3 sync_inventory_ledger.py" in stub_client.received["prompt"]
    assert "/Users/dev/project" in stub_client.received["prompt"]
    assert "python3 sync_inventory_ledger.py" not in stub_client.received["system"]
    assert stub_client.received["tool_name"] == judge.TOOL_NAME
    assert stub_client.received["input_schema"] == judge.INPUT_SCHEMA


def test_run_watchedCommand_cachesSystemPrompt(monkeypatch):
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 train_model.py"))

    assert stub_client.received["cache_system"] is True


def test_run_watchedCommand_autoModeContextIncludedInSystemPrompt(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "autoMode": {
                    "environment": ["$defaults", "Org: Acme Corp, ad-tech"],
                    "hard_deny": ["Never modify prod without asking"],
                    "soft_deny": ["Never run prod ops without asking first"],
                    "allow": ["Read-only shell inspection is allowed"],
                }
            }
        )
    )
    monkeypatch.setattr(judge, "SETTINGS_PATH", settings_path)
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 train_model.py"))

    system_prompt = stub_client.received["system"]
    assert "Org: Acme Corp, ad-tech" in system_prompt
    assert "Never modify prod without asking" in system_prompt
    assert "Never run prod ops without asking first" in system_prompt
    assert "Read-only shell inspection is allowed" in system_prompt
    assert "$defaults" not in system_prompt


def _run_main(hook_input: dict, monkeypatch, capsys) -> dict:
    stdin = io.StringIO(json.dumps(hook_input))
    monkeypatch.setattr(sys, "stdin", stdin)
    judge.main()
    return json.loads(capsys.readouterr().out)


def test_main_happyPath_writesDecisionJsonToStdout(monkeypatch, capsys):
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    hook_input = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 -c 'print(1)'"},
        "session_id": "sess-1",
        "cwd": "/tmp",
    }

    result = _run_main(hook_input, monkeypatch, capsys)

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_main_unexpectedExceptionInRun_stillPrintsEmptyJson(monkeypatch, capsys):
    def _raise(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(judge, "run", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    judge.main()

    assert json.loads(capsys.readouterr().out) == {}
