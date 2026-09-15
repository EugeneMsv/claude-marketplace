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


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Clear this plugin's own env vars before every test.

    This repo is also the installed plugin source, so the developer's live
    ~/.claude/settings.json `env` block leaks straight into the test process.
    Without this, tests that exercise default behaviour silently assert against
    whatever the machine happens to be configured for - setting
    PERMISSIONS_JUDITOR_REASONING_ENABLED=false in real settings was enough to
    fail a schema assertion here. Tests that care about a value set it
    explicitly via monkeypatch.setenv.
    """
    for name in (
        judge.WATCHED_COMMANDS_ENV_VAR,
        judge.SEGMENTER_ENV_VAR,
        judge.MODEL_ENV_VAR,
        judge.EFFORT_ENV_VAR,
        judge.REASONING_ENABLED_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_log_decidedRecordWithTimings_ordersTotalBeforeHttpBeforeReasoning():
    judge._log(
        {
            "session_id": "sess-1",
            "command": "python3 -c 'print(1)'",
            "outcome": "decided",
            "decision": "allow",
            "total_ms": 901,
            "http_ms": 842,
            "reasoning": "pure computation",
        }
    )

    [record] = _log_lines()
    assert list(record.keys()) == [
        "timestamp",
        "outcome",
        "decision",
        "total_ms",
        "http_ms",
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


def test_resolveModel_anthropicDefaultSonnetModelSet_usesEnvValue():
    env = {"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6"}

    assert judge.resolve_model(env) == "claude-sonnet-4-6"


def test_resolveModel_envVarUnset_usesDefault():
    assert judge.resolve_model({}) == "claude-sonnet-5"


def test_resolveModel_permissionsJuditorModelSet_takesPriorityOverAnthropicDefault():
    env = {
        judge.MODEL_ENV_VAR: "claude-haiku-4-5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
    }

    assert judge.resolve_model(env) == "claude-haiku-4-5"


def test_resolveModel_permissionsJuditorModelSetAlone_usesItOverDefault():
    env = {judge.MODEL_ENV_VAR: "claude-haiku-4-5"}

    assert judge.resolve_model(env) == "claude-haiku-4-5"


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


def test_resolveWatchedPatterns_mixedBashAndMcpPatterns_parsesEachEntry():
    """The same env var covers both domains - a Bash prefix and an MCP
    tool-name glob can sit in the same comma-separated list."""
    env = {judge.WATCHED_COMMANDS_ENV_VAR: "python3,mcp__atlassian__*"}

    assert judge.resolve_watched_patterns(env) == ("python3*", "mcp__atlassian__*")


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


# --- is_watched_mcp_tool --------------------------------------------------------


def test_isWatchedMcpTool_matchingPattern_returnsTrue():
    assert judge.is_watched_mcp_tool("mcp__atlassian__search", ("mcp__atlassian__*",)) is True


def test_isWatchedMcpTool_noPatterns_returnsFalse():
    assert judge.is_watched_mcp_tool("mcp__atlassian__search", ()) is False


def test_isWatchedMcpTool_nonMatchingPattern_returnsFalse():
    assert judge.is_watched_mcp_tool("mcp__slack__slack_send_message", ("mcp__atlassian__*",)) is False


def test_isWatchedMcpTool_exactToolNamePattern_matchesOnlyThatTool():
    patterns = ("mcp__atlassian__createJiraIssue",)

    assert judge.is_watched_mcp_tool("mcp__atlassian__createJiraIssue", patterns) is True
    assert judge.is_watched_mcp_tool("mcp__atlassian__getConfluencePage", patterns) is False


def test_isWatchedMcpTool_defaultBashPattern_neverMatchesMcpTool():
    """DEFAULT_WATCHED_COMMANDS ("python3*",) must not accidentally watch every
    MCP tool by default - MCP scanning is opt-in per tool/server."""
    assert judge.is_watched_mcp_tool("mcp__atlassian__search", judge.resolve_watched_patterns({})) is False


# --- build_mcp_subject -----------------------------------------------------------


def test_buildMcpSubject_emptyParams_rendersEmptyJsonObject():
    subject = judge.build_mcp_subject("mcp__trino__list_catalogs", {})

    assert subject == "MCP tool `mcp__trino__list_catalogs` invoked with parameters: {}"


def test_buildMcpSubject_typicalParams_rendersToolNameAndJson():
    tool_input = {"query": "SELECT count(*) FROM orders LIMIT 10", "catalog": "hive"}

    subject = judge.build_mcp_subject("mcp__trino__execute_query", tool_input)

    assert subject.startswith("MCP tool `mcp__trino__execute_query` invoked with parameters: ")
    assert json.loads(subject.split("parameters: ", 1)[1]) == tool_input


def test_buildMcpSubject_oversizedParams_truncatesToMaxChars():
    tool_input = {"body": "x" * (judge.MAX_MCP_PARAMS_CHARS * 2)}

    subject = judge.build_mcp_subject("mcp__slack__slack_send_message", tool_input)

    params_text = subject.split("parameters: ", 1)[1]
    assert len(params_text) == judge.MAX_MCP_PARAMS_CHARS


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


# --- load_reference_mcp_rules ----------------------------------------------------


def test_loadReferenceMcpRules_missingFile_returnsEmptyLists(tmp_path):
    result = judge.load_reference_mcp_rules(tmp_path / "does-not-exist.json")

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceMcpRules_malformedJson_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json")

    result = judge.load_reference_mcp_rules(settings_path)

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceMcpRules_mixedMcpAndNonMcpEntries_filtersToOnlyMcp(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["mcp__atlassian__search", "Bash(git status)"],
                    "ask": ["mcp__atlassian__createJiraIssue", "Edit(*.py)"],
                    "deny": ["mcp__confluence__confluence_delete_page"],
                }
            }
        )
    )

    result = judge.load_reference_mcp_rules(settings_path)

    assert result == {
        "allow": ["mcp__atlassian__search"],
        "ask": ["mcp__atlassian__createJiraIssue"],
        "deny": ["mcp__confluence__confluence_delete_page"],
    }


def test_loadReferenceMcpRules_emptyPermissionLists_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"permissions": {"allow": [], "ask": [], "deny": []}}))

    result = judge.load_reference_mcp_rules(settings_path)

    assert result == {"allow": [], "ask": [], "deny": []}


def test_loadReferenceMcpRules_noPermissionsKey_returnsEmptyLists(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"someOtherKey": True}))

    result = judge.load_reference_mcp_rules(settings_path)

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


def _mcp_hook_input(tool_name, tool_input, session_id="sess-1", cwd="/tmp/project"):
    return json.dumps(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": tool_name,
            "tool_input": tool_input,
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
    for field in ("total_ms", "http_ms"):
        assert isinstance(record[field], int)
        assert record[field] >= 0
    # total_ms starts at module import, so it can never be shorter than the
    # round-trip it contains.
    assert record["total_ms"] >= record["http_ms"]


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
    monkeypatch.delenv(judge.EFFORT_ENV_VAR, raising=False)
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


def test_run_llmRaises_asksForReviewAndLogsError(monkeypatch):
    """A watched command this hook meant to judge but couldn't must NOT fall
    through to {} - that would let the user's own allow rules auto-approve it
    with no judgment at all."""
    stub_client = _StubClient(raises=RuntimeError("boom"))
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "ask"
    [record] = _log_lines()
    assert record["outcome"] == "error"
    assert record["decision"] == "ask"
    assert "boom" in record["error"]


def test_run_invalidDecisionValue_asksForReviewAndLogsError(monkeypatch):
    stub_client = _StubClient(result={"decision": "maybe", "reasoning": "unsure"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -c 'print(1)'"))

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "ask"
    [record] = _log_lines()
    assert record["outcome"] == "error"
    assert record["decision"] == "ask"
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
    assert stub_client.received["input_schema"] == judge.build_input_schema(
        judge.DEFAULT_REASONING_ENABLED
    )


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


# --- build_system_prompt: MCP long-range-scan guidance ---------------------------


def test_buildSystemPrompt_mentionsLongRangeSqlScanGuidance():
    """Regression guard: a read-only SQL query spanning months/years on a
    large table must still be steered toward "ask" - the guidance and its
    few-shot example live as static prose in SYSTEM_TEMPLATE, not behind any
    formatted placeholder, so nothing else exercises this text."""
    empty_rules = {"allow": [], "ask": [], "deny": []}
    empty_auto_mode = {"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}

    system_prompt = judge.build_system_prompt(empty_rules, empty_auto_mode)

    assert "long time range" in system_prompt
    assert "months or years" in system_prompt


def test_buildSystemPrompt_mentionsPartitionsMetadataIsCheapNotAScan():
    """Regression guard: $partitions catalog lookups must not be confused
    with a real wide-range data scan - both live as static prose/examples in
    SYSTEM_TEMPLATE, not behind any formatted placeholder."""
    empty_rules = {"allow": [], "ask": [], "deny": []}
    empty_auto_mode = {"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}

    system_prompt = judge.build_system_prompt(empty_rules, empty_auto_mode)

    assert "$partitions" in system_prompt
    assert 'orders$partitions' in system_prompt


def test_buildSystemPrompt_mentionsGrafanaWideTimeRangeGuidance():
    """Regression guard: a read-only Grafana/observability query spanning
    more than about a week must still be steered toward "ask"."""
    empty_rules = {"allow": [], "ask": [], "deny": []}
    empty_auto_mode = {"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}

    system_prompt = judge.build_system_prompt(empty_rules, empty_auto_mode)

    assert "now-7d" in system_prompt
    assert "now-90d" in system_prompt
    assert "regardless of how the range is expressed" in system_prompt
    assert "2026-01-01" in system_prompt


# --- run(): MCP tool path -------------------------------------------------------


def test_run_mcpToolWatched_returnsAllowBehaviorAndLogsDecidedWithToolName(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__atlassian__*")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "read-only fetch"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_mcp_hook_input("mcp__atlassian__getConfluencePage", {"pageId": "123456"}))

    assert result["hookSpecificOutput"]["decision"] == {"behavior": "allow", "message": "read-only fetch"}
    [record] = _log_lines()
    assert record["outcome"] == "decided"
    assert record["tool_name"] == "mcp__atlassian__getConfluencePage"


def test_run_mcpToolUnwatchedByDefault_returnsEmptyAndLogsSkipUnwatchedCommand(monkeypatch):
    """No MCP tool is scanned unless explicitly added to
    PERMISSIONS_JUDITOR_WATCHED_COMMANDS - the default (python3 only) must
    not silently start judging every MCP call."""
    monkeypatch.delenv(judge.WATCHED_COMMANDS_ENV_VAR, raising=False)
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))

    result = judge.run(_mcp_hook_input("mcp__atlassian__getConfluencePage", {"pageId": "123456"}))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_unwatched_command"


def test_run_mcpToolNotInWatchedList_returnsEmptyAndLogsSkipUnwatchedCommand(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__atlassian__*")
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True))

    result = judge.run(_mcp_hook_input("mcp__slack__slack_send_message", {"channel": "#general"}))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_unwatched_command"


def test_run_mcpToolNoCredentials_returnsEmptyAndLogsSkipNoCredentials(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__atlassian__*")
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(False))

    result = judge.run(_mcp_hook_input("mcp__atlassian__getConfluencePage", {"pageId": "123456"}))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_no_credentials"


def test_run_mcpTool_sendsToolNameAndParamsInPromptNotSystem(monkeypatch):
    """cwd/tool-call subject are the per-call variable part - they belong in
    the user prompt, never in the cacheable system block. Uses a pageId not
    reused by any SYSTEM_TEMPLATE few-shot example, so a false-negative match
    against static example text can't hide a real leak into system."""
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__atlassian__*")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_mcp_hook_input("mcp__atlassian__getConfluencePage", {"pageId": "unique-page-id-42"}))

    assert "mcp__atlassian__getConfluencePage" in stub_client.received["prompt"]
    assert "unique-page-id-42" in stub_client.received["prompt"]
    assert "unique-page-id-42" not in stub_client.received["system"]


def test_run_mcpTool_systemPromptUsesMcpReferenceRulesNotBashRules(monkeypatch, tmp_path):
    """mcp__github__deleteRepository doesn't appear in any SYSTEM_TEMPLATE
    few-shot example, so a match against static example text can't produce a
    false pass here (unlike a rule string the template's own examples reuse)."""
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__atlassian__*")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "deny": ["mcp__github__deleteRepository", "Bash(rm -rf *)"],
                }
            }
        )
    )
    monkeypatch.setattr(judge, "SETTINGS_PATH", settings_path)
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_mcp_hook_input("mcp__atlassian__getConfluencePage", {"pageId": "123456"}))

    assert "mcp__github__deleteRepository" in stub_client.received["system"]
    assert "Bash(rm -rf *)" not in stub_client.received["system"]


def test_run_bashCommand_systemPromptUsesBashReferenceRulesNotMcpRules(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "deny": ["mcp__github__deleteRepository", "Bash(rm -rf *)"],
                }
            }
        )
    )
    monkeypatch.setattr(judge, "SETTINGS_PATH", settings_path)
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    judge.run(_hook_input("python3 -c 'print(1)'"))

    assert "Bash(rm -rf *)" in stub_client.received["system"]
    assert "mcp__github__deleteRepository" not in stub_client.received["system"]


def test_run_mcpDenyDecision_returnsDenyBehaviorWithMessage(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__slack__*")
    stub_client = _StubClient(result={"decision": "deny", "reasoning": "sends unsolicited external message"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_mcp_hook_input("mcp__slack__slack_send_message", {"channel": "#general", "text": "..."}))

    assert result["hookSpecificOutput"]["decision"] == {
        "behavior": "deny",
        "message": "sends unsolicited external message",
    }


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


# --- Over-long commands / truncated MCP params / shlex-first segmentation ----


def test_run_commandOverMaxChars_deniesWithSplitInstructionAndNeverCallsModel(monkeypatch):
    """Judging only the first MAX_COMMAND_CHARS is a bypass, not a truncation:
    a benign prefix would clear a destructive tail the model never sees."""
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "looks fine"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    long_command = "python3 -c \"print('" + ("x" * judge.MAX_COMMAND_CHARS) + "')\""
    assert len(long_command) > judge.MAX_COMMAND_CHARS

    result = judge.run(_hook_input(long_command))

    decision = result["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "Split it into several smaller commands" in decision["message"]
    assert stub_client.received is None, "must not spend a model call on an unjudgeable command"
    [record] = _log_lines()
    assert record["decision"] == "deny"
    assert record["http_ms"] is None


def test_run_commandExactlyAtMaxChars_stillJudgedByModel(monkeypatch):
    """The cap is the last fully-readable size, so it must not trip the deny."""
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    command = "python3 " + "x" * (judge.MAX_COMMAND_CHARS - len("python3 "))
    assert len(command) == judge.MAX_COMMAND_CHARS

    result = judge.run(_hook_input(command))

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_run_unwatchedCommandOverMaxChars_staysOutOfScope(monkeypatch):
    """Length is only this hook's business for commands it actually watches."""
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "docker")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "safe"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("echo " + "y" * (judge.MAX_COMMAND_CHARS + 50)))

    assert result == {}
    [record] = _log_lines()
    assert record["outcome"] == "skip_unwatched_command"


def test_run_mcpParamsOverCapAndModelAllows_escalatesToAsk(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__trino__*")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "read-only select"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))
    huge_query = "SELECT " + ("col, " * judge.MAX_MCP_PARAMS_CHARS) + "1"

    result = judge.run(_mcp_hook_input("mcp__trino__execute_query", {"query": huge_query}))

    decision = result["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "ask"
    assert "never judged" in decision["message"]


def test_run_mcpParamsUnderCapAndModelAllows_staysAllow(monkeypatch):
    monkeypatch.setenv(judge.WATCHED_COMMANDS_ENV_VAR, "mcp__trino__*")
    stub_client = _StubClient(result={"decision": "allow", "reasoning": "read-only select"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_mcp_hook_input("mcp__trino__execute_query", {"query": "SELECT 1"}))

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_isWatchedCommand_bashlexModeShlexHit_doesNotImportBashlex(monkeypatch):
    """bashlex can only widen the match set, so a shlex hit is already final -
    the ~55ms lazy venv import must not be paid on that path."""
    monkeypatch.setenv(judge.SEGMENTER_ENV_VAR, "bashlex")
    called = []
    monkeypatch.setattr(judge, "_import_bashlex", lambda: called.append(True))

    assert judge.is_watched_command("python3 script.py", ("python3*",)) is True
    assert called == []


def test_isWatchedCommand_bashlexModeShlexMiss_fallsThroughToBashlex(monkeypatch):
    """The for-loop body hides the command from shlex's flat split, which is
    exactly the blind spot bashlex mode exists to cover."""
    monkeypatch.setenv(judge.SEGMENTER_ENV_VAR, "bashlex")
    command = 'for f in a b; do grep -n needle "$f"; done'

    assert judge.is_watched_command(command, ("grep*",), env={judge.SEGMENTER_ENV_VAR: "shlex"}) is False
    assert judge.is_watched_command(command, ("grep*",), env={judge.SEGMENTER_ENV_VAR: "bashlex"}) is True


def test_isWatchedCommand_bashlexUnavailableAndShlexMisses_returnsFalseNotRaises(monkeypatch):
    monkeypatch.setattr(judge, "_import_bashlex", lambda: (_ for _ in ()).throw(ImportError("no bashlex")))

    result = judge.is_watched_command(
        'for f in a b; do grep -n needle "$f"; done',
        ("grep*",),
        env={judge.SEGMENTER_ENV_VAR: "bashlex"},
    )

    assert result is False


# --- reasoning mode (PERMISSIONS_JUDITOR_REASONING) ---------------------------


def test_resolveReasoningEnabled_envVarUnset_defaultsToTrue():
    assert judge.resolve_reasoning_enabled({}) is True


@pytest.mark.parametrize("value", ["false", "FALSE", "False", " false "])
def test_resolveReasoningEnabled_explicitFalse_returnsFalseCaseInsensitively(value):
    assert judge.resolve_reasoning_enabled({judge.REASONING_ENABLED_ENV_VAR: value}) is False


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_resolveReasoningEnabled_explicitTrue_returnsTrue(value):
    assert judge.resolve_reasoning_enabled({judge.REASONING_ENABLED_ENV_VAR: value}) is True


@pytest.mark.parametrize("value", ["sideways", "0", "no", "", "1"])
def test_resolveReasoningEnabled_unrecognizedValue_staysEnabled(value):
    """Never silently drop the rationale on a typo - anything that isn't an
    explicit "false" keeps the mode that still explains itself on an ask/deny."""
    assert judge.resolve_reasoning_enabled({judge.REASONING_ENABLED_ENV_VAR: value}) is True


@pytest.mark.parametrize(
    "reasoning_enabled,expected_order",
    [
        (True, ["reasoning", "decision"]),
        (False, ["decision"]),
    ],
)
def test_buildInputSchema_propertyOrderMatchesSetting(reasoning_enabled, expected_order):
    """Property order decides generation order, so it IS the feature here: when
    enabled, the rationale must come first for the verdict to be conditioned
    on it."""
    schema = judge.build_input_schema(reasoning_enabled)

    assert list(schema["properties"]) == expected_order
    assert schema["required"] == expected_order
    assert schema["additionalProperties"] is False


def test_run_reasoningDisabled_sendsDecisionOnlySchemaAndStillReturnsAMessage(monkeypatch):
    """With reasoning off the model returns no rationale, but an ask/deny is
    surfaced to the user and must not carry an empty message."""
    monkeypatch.setenv(judge.REASONING_ENABLED_ENV_VAR, "false")
    stub_client = _StubClient(result={"decision": "ask"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 deploy.py"))

    assert list(stub_client.received["input_schema"]["properties"]) == ["decision"]
    decision = result["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "ask"
    assert decision["message"] == judge.NO_REASONING_MESSAGE


def test_run_reasoningEnabled_sendsRationaleFirstAndUsesItAsMessage(monkeypatch):
    monkeypatch.setenv(judge.REASONING_ENABLED_ENV_VAR, "true")
    stub_client = _StubClient(result={"reasoning": "opens a listener", "decision": "ask"})
    monkeypatch.setattr(judge, "AnthropicClient", _stub_anthropic_client(True, stub_client))

    result = judge.run(_hook_input("python3 -m http.server 8000"))

    assert list(stub_client.received["input_schema"]["properties"]) == ["reasoning", "decision"]
    assert result["hookSpecificOutput"]["decision"]["message"] == "opens a listener"
