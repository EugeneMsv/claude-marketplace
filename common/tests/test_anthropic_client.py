"""Tests for AnthropicClient.complete and credential resolution."""

import io
import json
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic_client import AnthropicClient, CredentialsMissingError


@pytest.fixture(autouse=True)
def _clean_hooks_llm_env(monkeypatch):
    """Ensure HOOKS_LLM_URL/HOOKS_LLM_AUTH_TOKEN start unset for every test,
    regardless of the real environment - tests that need them set do so
    explicitly via monkeypatch.setenv."""
    monkeypatch.delenv("HOOKS_LLM_URL", raising=False)
    monkeypatch.delenv("HOOKS_LLM_AUTH_TOKEN", raising=False)


def _make_response(body: dict):
    """Build a context-manager mock matching urllib.request.urlopen's response object."""
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_complete_textBlockFirst_returnsText():
    body = {"content": [{"type": "text", "text": "  Score: 80/100  "}]}
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        result = client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10)

    assert result == "Score: 80/100"


def test_complete_thinkingBlockFirst_skipsToTextBlock():
    body = {
        "content": [
            {"type": "thinking", "thinking": "reasoning...", "signature": "abc"},
            {"type": "text", "text": "NONE"},
        ]
    }
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        result = client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10)

    assert result == "NONE"


def test_complete_noTextBlock_returnsEmptyString():
    body = {"content": [{"type": "thinking", "thinking": "reasoning...", "signature": "abc"}]}
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        result = client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10)

    assert result == ""


def test_init_noCredentials_raisesCredentialsMissingError():
    with pytest.raises(CredentialsMissingError):
        AnthropicClient()


def test_hasCredentials_apiKeySet_returnsTrue(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    assert AnthropicClient.has_credentials() is True


def test_hasCredentials_noCredentialsSetAndNotDarwin_returnsFalse(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    assert AnthropicClient.has_credentials() is False


def _keychain_credential_json(access_token="oauth-token-value", expires_in_seconds=3600):
    return json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": access_token,
                "expiresAt": int((time.time() + expires_in_seconds) * 1000),
            }
        }
    )


def _fake_run_returning(stdout: str):
    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)

    return _fake_run


def _fake_run_raising(exc: Exception):
    def _fake_run(*args, **kwargs):
        raise exc

    return _fake_run


def test_hasCredentials_noEnvVarsButValidKeychainToken_returnsTrue(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", _fake_run_returning(_keychain_credential_json()))

    assert AnthropicClient.has_credentials() is True


def test_hasCredentials_noEnvVarsAndExpiredKeychainToken_returnsFalse(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess, "run", _fake_run_returning(_keychain_credential_json(expires_in_seconds=-60))
    )

    assert AnthropicClient.has_credentials() is False


def test_hasCredentials_noEnvVarsAndKeychainLookupFails_returnsFalse(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run_raising(subprocess.CalledProcessError(returncode=44, cmd=["security"])),
    )

    assert AnthropicClient.has_credentials() is False


def test_hasCredentials_noEnvVarsAndKeychainReturnsMalformedJson_returnsFalse(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", _fake_run_returning("not json"))

    assert AnthropicClient.has_credentials() is False


def test_fromEnv_apiKeySet_neverConsultsKeychain(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("keychain should not be consulted when an env var is set")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    client = AnthropicClient.from_env()

    assert client._api_key == "test-key"
    assert client._auth_token is None


def test_fromEnv_noEnvVarsValidKeychainToken_usesItAsAuthToken(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess, "run", _fake_run_returning(_keychain_credential_json("oauth-token-value"))
    )

    client = AnthropicClient.from_env()

    assert client._api_key is None
    assert client._auth_token == "oauth-token-value"


# --- HOOKS_LLM_URL / HOOKS_LLM_AUTH_TOKEN resolution tier -----------------------


def test_hasCredentials_hooksLlmUrlAndAuthTokenSet_returnsTrue(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_URL", "https://proxy.example.com")
    monkeypatch.setenv("HOOKS_LLM_AUTH_TOKEN", "hooks-token")

    assert AnthropicClient.has_credentials() is True


def test_hasCredentials_onlyHooksLlmUrlSet_fallsThroughToNextTier(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_URL", "https://proxy.example.com")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    assert AnthropicClient.has_credentials() is False


def test_hasCredentials_onlyHooksLlmAuthTokenSet_fallsThroughToNextTier(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_AUTH_TOKEN", "hooks-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    assert AnthropicClient.has_credentials() is False


def test_fromEnv_hooksLlmVarsSet_usesHooksLlmUrlAsBaseUrlAndTokenAsAuthToken(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_URL", "https://proxy.example.com")
    monkeypatch.setenv("HOOKS_LLM_AUTH_TOKEN", "hooks-token")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    client = AnthropicClient.from_env()

    assert client._base_url == "https://proxy.example.com"
    assert client._api_key is None
    assert client._auth_token == "hooks-token"


def test_fromEnv_hooksLlmVarsSet_takesPriorityOverAnthropicApiKey(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_URL", "https://proxy.example.com")
    monkeypatch.setenv("HOOKS_LLM_AUTH_TOKEN", "hooks-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-ignored")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("keychain should not be consulted when HOOKS_LLM_* vars are set")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    client = AnthropicClient.from_env()

    assert client._api_key is None
    assert client._auth_token == "hooks-token"
    assert client._base_url == "https://proxy.example.com"


def test_fromEnv_hooksLlmUrlOverridesAnthropicBaseUrl(monkeypatch):
    monkeypatch.setenv("HOOKS_LLM_URL", "https://proxy.example.com")
    monkeypatch.setenv("HOOKS_LLM_AUTH_TOKEN", "hooks-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://should-be-ignored.example.com")

    client = AnthropicClient.from_env()

    assert client._base_url == "https://proxy.example.com"


_TOOL_NAME = "classify_command_security"
_TOOL_DESCRIPTION = "Classify the security risk of a shell command."
_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["allow", "ask", "deny"]},
        "reasoning": {"type": "string"},
    },
    "required": ["decision", "reasoning"],
}


def test_completeWithTool_toolUseBlockMatchesName_returnsInputDict():
    body = {
        "content": [
            {"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "allow", "reasoning": "safe"}}
        ]
    }
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        result = client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_INPUT_SCHEMA,
            max_tokens=300,
        )

    assert result == {"decision": "allow", "reasoning": "safe"}


def test_completeWithTool_thinkingBlockBeforeToolUse_skipsToToolUseBlock():
    body = {
        "content": [
            {"type": "thinking", "thinking": "reasoning...", "signature": "abc"},
            {"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "deny", "reasoning": "destructive"}},
        ]
    }
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        result = client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: rm -rf /",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_INPUT_SCHEMA,
            max_tokens=300,
        )

    assert result == {"decision": "deny", "reasoning": "destructive"}


def test_completeWithTool_noToolUseBlock_raisesValueError():
    body = {"content": [{"type": "text", "text": "I refuse to use the tool."}]}
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        with pytest.raises(ValueError, match=_TOOL_NAME):
            client.complete_with_tool(
                model="claude-sonnet-5",
                prompt="Classify: python3 -c 'print(1)'",
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=_INPUT_SCHEMA,
                max_tokens=300,
            )


def test_completeWithTool_buildsRequestWithToolChoiceAndStrictSchema():
    body = {
        "content": [
            {"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "ask", "reasoning": "uncertain"}}
        ]
    }
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)) as mock_urlopen:
        client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -m http.server",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_INPUT_SCHEMA,
            max_tokens=300,
        )

    sent_request = mock_urlopen.call_args[0][0]
    payload = json.loads(sent_request.data.decode("utf-8"))

    assert payload["tools"] == [
        {
            "name": _TOOL_NAME,
            "description": _TOOL_DESCRIPTION,
            "input_schema": {**_INPUT_SCHEMA, "additionalProperties": False},
            "strict": True,
        }
    ]
    assert payload["tool_choice"] == {"type": "tool", "name": _TOOL_NAME}
    assert payload["model"] == "claude-sonnet-5"
    assert payload["max_tokens"] == 300


def test_completeWithTool_schemaMissingAdditionalProperties_defaultsToFalse():
    """The API rejects a strict object schema with HTTP 400 unless
    additionalProperties is explicitly set - this must be defaulted rather
    than left for every caller to remember."""
    body = {"content": [{"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "allow", "reasoning": "safe"}}]}
    client = AnthropicClient(api_key="test-key")
    schema_without_it = {k: v for k, v in _INPUT_SCHEMA.items() if k != "additionalProperties"}

    with patch("urllib.request.urlopen", return_value=_make_response(body)) as mock_urlopen:
        client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=schema_without_it,
            max_tokens=300,
        )

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert payload["tools"][0]["input_schema"]["additionalProperties"] is False


def test_completeWithTool_schemaWithExplicitAdditionalProperties_respectsCallerValue():
    body = {"content": [{"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "allow", "reasoning": "safe"}}]}
    client = AnthropicClient(api_key="test-key")
    schema_with_true = {**_INPUT_SCHEMA, "additionalProperties": True}

    with patch("urllib.request.urlopen", return_value=_make_response(body)) as mock_urlopen:
        client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=schema_with_true,
            max_tokens=300,
        )

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert payload["tools"][0]["input_schema"]["additionalProperties"] is True


def test_completeWithTool_doesNotMutateCallersSchemaDict():
    body = {"content": [{"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "allow", "reasoning": "safe"}}]}
    client = AnthropicClient(api_key="test-key")
    schema_without_it = {k: v for k, v in _INPUT_SCHEMA.items() if k != "additionalProperties"}
    original = dict(schema_without_it)

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=schema_without_it,
            max_tokens=300,
        )

    assert schema_without_it == original


def test_completeWithTool_toolUseBlockWrongName_raisesValueError():
    body = {
        "content": [
            {"type": "tool_use", "name": "some_other_tool", "input": {"unexpected": "shape"}}
        ]
    }
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", return_value=_make_response(body)):
        with pytest.raises(ValueError, match=_TOOL_NAME):
            client.complete_with_tool(
                model="claude-sonnet-5",
                prompt="Classify: python3 -c 'print(1)'",
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=_INPUT_SCHEMA,
                max_tokens=300,
            )


# ── effort / thinking tuning ─────────────────────────────────────────────

_TEXT_BODY = {"content": [{"type": "text", "text": "ok"}]}
_TOOL_BODY = {
    "content": [
        {"type": "tool_use", "name": _TOOL_NAME, "input": {"decision": "allow", "reasoning": "safe"}}
    ]
}


def _capture_complete_payload(**kwargs) -> dict:
    """Run complete() against a stubbed response and return the sent payload."""
    client = AnthropicClient(api_key="test-key")
    with patch("urllib.request.urlopen", return_value=_make_response(_TEXT_BODY)) as mock_urlopen:
        client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10, **kwargs)
    return json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))


def _capture_tool_payload(**kwargs) -> dict:
    """Run complete_with_tool() against a stubbed response and return the sent payload."""
    client = AnthropicClient(api_key="test-key")
    with patch("urllib.request.urlopen", return_value=_make_response(_TOOL_BODY)) as mock_urlopen:
        client.complete_with_tool(
            model="claude-sonnet-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_INPUT_SCHEMA,
            max_tokens=300,
            **kwargs,
        )
    return json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_effort_notPassed_defaultsToMedium(capture):
    payload = capture()

    assert payload["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_effort_none_omitsOutputConfig(capture):
    """Haiku 4.5 and earlier reject output_config.effort with HTTP 400, so
    callers on those models must be able to drop the key entirely."""
    payload = capture(effort=None)

    assert "output_config" not in payload


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
@pytest.mark.parametrize("level", ["max", "xhigh", "high", "medium", "low"])
def test_effort_validLevel_sentVerbatim(capture, level):
    payload = capture(effort=level)

    assert payload["output_config"]["effort"] == level


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
@pytest.mark.parametrize("bad", ["extreme", "HIGH", "", "minimal"])
def test_effort_invalidLevel_raisesValueError(capture, bad):
    with pytest.raises(ValueError, match="effort must be one of"):
        capture(effort=bad)


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_effort_adaptive_raisesValueErrorPointingAtThinking(capture):
    """'adaptive' is a thinking mode, not an effort level - the error has to
    say so, since mixing them up is the obvious failure once both knobs exist."""
    with pytest.raises(ValueError, match="thinking mode, not an effort level"):
        capture(effort="adaptive")


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_thinking_notPassed_omitsThinking(capture):
    payload = capture()

    assert "thinking" not in payload


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_thinking_stringShorthand_expandsToTypeDict(capture):
    payload = capture(thinking="adaptive")

    assert payload["thinking"] == {"type": "adaptive"}


def test_thinking_explicitDict_passedThroughUnchanged():
    payload = _capture_complete_payload(thinking={"type": "enabled", "budget_tokens": 2048})

    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
@pytest.mark.parametrize("bad", ["on", "budget", {"type": "auto"}, {}])
def test_thinking_invalidType_raisesValueError(capture, bad):
    with pytest.raises(ValueError, match="thinking type must be one of"):
        capture(thinking=bad)


@pytest.mark.parametrize("thinking", ["enabled", {"type": "enabled", "budget_tokens": 2048}])
def test_completeWithTool_thinkingEnabled_raisesValueError(thinking):
    """Manual extended thinking is incompatible with a tool_choice that forces
    tool use; the API errors, so reject it before the round trip."""
    with pytest.raises(ValueError, match="incompatible with forced tool_choice"):
        _capture_tool_payload(thinking=thinking)


def test_completeWithTool_thinkingAdaptive_allowed():
    """Adaptive thinking does support forced tool use, unlike manual mode."""
    payload = _capture_tool_payload(thinking="adaptive")

    assert payload["thinking"] == {"type": "adaptive"}


def test_completeWithTool_effortAndThinking_bothPresentAlongsideToolChoice():
    payload = _capture_tool_payload(effort="low", thinking="adaptive")

    assert payload["output_config"]["effort"] == "low"
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["tool_choice"] == {"type": "tool", "name": _TOOL_NAME}
    assert payload["tools"][0]["strict"] is True


# ── 400 strip-and-retry fallback ──────────────────────────────────────────


def _http_error(body: dict) -> urllib.error.HTTPError:
    fp = io.BytesIO(json.dumps(body).encode("utf-8"))
    return urllib.error.HTTPError(url="https://api.anthropic.com/v1/messages", code=400, msg="Bad Request", hdrs=None, fp=fp)


def test_post_tuningRejected_retriesOnceWithoutEffortOrThinking():
    """A 400 naming effort/thinking as the offending field means the model
    doesn't support the key at all (Haiku 4.5 and earlier) - strip and retry
    once rather than failing open on every call to that model."""
    rejection = _http_error({"error": {"type": "invalid_request_error", "message": "output_config.effort: Extra inputs are not permitted"}})
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", side_effect=[rejection, _make_response(_TEXT_BODY)]) as mock_urlopen:
        result = client.complete(model="claude-haiku-4-5", prompt="hi", max_tokens=10, effort="medium")

    assert result == "ok"
    assert mock_urlopen.call_count == 2
    retry_payload = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert "output_config" not in retry_payload
    assert "thinking" not in retry_payload


def test_post_tuningRejected_retryPreservesOtherOutputConfigKeys():
    """Stripping effort must not drop unrelated output_config keys, like the
    structured-output schema complete_with_tool sends alongside it."""
    rejection = _http_error({"error": {"message": "thinking is not supported for this model"}})
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", side_effect=[rejection, _make_response(_TOOL_BODY)]) as mock_urlopen:
        client.complete_with_tool(
            model="claude-haiku-4-5",
            prompt="Classify: python3 -c 'print(1)'",
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=_INPUT_SCHEMA,
            max_tokens=300,
            effort="medium",
            thinking="adaptive",
        )

    retry_payload = json.loads(mock_urlopen.call_args_list[1][0][0].data.decode("utf-8"))
    assert "thinking" not in retry_payload
    assert "effort" not in retry_payload.get("output_config", {})
    assert retry_payload["tool_choice"] == {"type": "tool", "name": _TOOL_NAME}


def test_post_unrelated400_propagatesWithoutRetry():
    """A 400 that isn't about effort/thinking (bad schema, bad model id) must
    surface immediately - retrying after stripping tuning keys would just
    mask the real cause."""
    rejection = _http_error({"error": {"message": "model: not found"}})
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", side_effect=[rejection]) as mock_urlopen:
        with pytest.raises(urllib.error.HTTPError):
            client.complete(model="nonexistent-model", prompt="hi", max_tokens=10, effort="medium")

    assert mock_urlopen.call_count == 1


def test_post_500_doesNotTriggerStripRetry():
    error = urllib.error.HTTPError(url="https://api.anthropic.com/v1/messages", code=500, msg="Internal Server Error", hdrs=None, fp=io.BytesIO(b"{}"))
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", side_effect=[error]) as mock_urlopen:
        with pytest.raises(urllib.error.HTTPError):
            client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10, effort="medium")

    assert mock_urlopen.call_count == 1


def test_post_400WithoutTuningInPayload_propagatesWithoutRetry():
    """If the payload never carried effort/thinking, there is nothing to
    strip - skip the retry path entirely rather than resending an identical
    request."""
    rejection = _http_error({"error": {"message": "output_config.effort: not permitted"}})
    client = AnthropicClient(api_key="test-key")

    with patch("urllib.request.urlopen", side_effect=[rejection]) as mock_urlopen:
        with pytest.raises(urllib.error.HTTPError):
            client.complete(model="claude-sonnet-4-6", prompt="hi", max_tokens=10, effort=None)

    assert mock_urlopen.call_count == 1


# ── system / cache_system ─────────────────────────────────────────────────


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_system_notPassed_omitsSystemKey(capture):
    payload = capture()

    assert "system" not in payload


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_system_passedWithoutCache_sendsTextBlockWithoutCacheControl(capture):
    payload = capture(system="static instructions")

    assert payload["system"] == [{"type": "text", "text": "static instructions"}]


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_system_cacheSystemTrue_addsEphemeralCacheControl(capture):
    payload = capture(system="static instructions", cache_system=True)

    assert payload["system"] == [
        {"type": "text", "text": "static instructions", "cache_control": {"type": "ephemeral"}}
    ]


@pytest.mark.parametrize("capture", [_capture_complete_payload, _capture_tool_payload])
def test_system_cacheSystemTrueButNoSystemText_staysOmitted(capture):
    """cache_system alone (no system text) has nothing to mark - must not
    produce a system key with no content."""
    payload = capture(cache_system=True)

    assert "system" not in payload


def test_completeWithTool_systemAndToolChoice_bothPresent():
    payload = _capture_tool_payload(system="static instructions", cache_system=True)

    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert payload["tool_choice"] == {"type": "tool", "name": _TOOL_NAME}
