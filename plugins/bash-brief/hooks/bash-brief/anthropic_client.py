#!/usr/bin/env python3
"""Minimal Anthropic-compatible Messages API client over the stdlib.

Single responsibility: send a one-shot prompt and return the text response.
Works against the public API or any proxy via ANTHROPIC_BASE_URL, and supports
both ``x-api-key`` and bearer ``auth-token`` credentials. Uses urllib so it has
no third-party dependency (the ``anthropic`` SDK is not assumed to be installed).

Canonical copy — do not edit the per-plugin duplicates under
plugins/<name>/hooks/<name>/anthropic_client.py directly. Edit this file, then
run scripts/sync-shared-files.sh to propagate the change.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"

# Users authenticated via Claude subscription/OAuth (rather than a raw
# ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN) have no credential exposed as an env
# var for hook subprocesses to use. Claude Code itself stores that session's
# OAuth token in the macOS Keychain under this service name; its accessToken
# works as a Bearer credential against the same public Messages API this
# client calls. This is an internal storage detail of Claude Code, not a
# documented/stable API, so every step here fails silently (falls through to
# "no credentials") rather than raising.
_MACOS_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _read_macos_keychain_oauth_token() -> str | None:
    """Return Claude Code's own session accessToken from the macOS Keychain, if
    present, unexpired, and parseable. Never raises."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", _MACOS_KEYCHAIN_SERVICE],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        oauth = json.loads(result.stdout)["claudeAiOauth"]
        access_token = oauth["accessToken"]
        expires_at_ms = oauth["expiresAt"]
    except (
        subprocess.SubprocessError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        return None

    if not access_token or time.time() * 1000 >= expires_at_ms:
        return None
    return access_token


class CredentialsMissingError(RuntimeError):
    """Raised when neither an API key nor an auth token is configured."""


class AnthropicClient:
    """Sends prompts to the Messages API. Construction resolves credentials once."""

    def __init__(self, base_url=None, api_key=None, auth_token=None, timeout=60):
        if not (api_key or auth_token):
            raise CredentialsMissingError
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._api_key = api_key
        self._auth_token = auth_token
        self._timeout = timeout

    @staticmethod
    def _resolve_credentials():
        """Return (api_key, auth_token). Prefers explicit env vars; falls back to
        the macOS Keychain OAuth token for subscription/OAuth-authenticated users."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if api_key or auth_token:
            return api_key, auth_token
        return None, _read_macos_keychain_oauth_token()

    @staticmethod
    def has_credentials() -> bool:
        """Whether any usable credential (env var or Keychain fallback) is available."""
        api_key, auth_token = AnthropicClient._resolve_credentials()
        return bool(api_key or auth_token)

    @classmethod
    def from_env(cls, timeout=60) -> "AnthropicClient":
        """Build a client from ANTHROPIC_* environment variables, falling back to
        the macOS Keychain OAuth token when neither env var is set."""
        api_key, auth_token = cls._resolve_credentials()
        return cls(
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
            api_key=api_key,
            auth_token=auth_token,
            timeout=timeout,
        )

    def _headers(self) -> dict:
        headers = {"content-type": "application/json", "anthropic-version": API_VERSION}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        else:
            headers["authorization"] = f"Bearer {self._auth_token}"
        return headers

    def complete(self, model: str, prompt: str, max_tokens: int) -> str:
        """Send a single user message and return the first text block, stripped."""
        payload = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/v1/messages",
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        # Some models prepend a "thinking" block — find the first text block instead
        # of assuming content[0] is text.
        for block in body["content"]:
            if block.get("type") == "text":
                return block["text"].strip()
        return ""
