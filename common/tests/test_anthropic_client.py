"""Tests for AnthropicClient.complete and credential resolution."""

import json
import subprocess
import sys
import time
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
