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
