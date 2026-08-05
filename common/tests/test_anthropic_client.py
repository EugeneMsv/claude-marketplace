"""Tests for AnthropicClient.complete and credential resolution."""

import json
import sys
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


def test_hasCredentials_noCredentialsSet_returnsFalse(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    assert AnthropicClient.has_credentials() is False
