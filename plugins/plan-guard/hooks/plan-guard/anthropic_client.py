#!/usr/bin/env python3
"""Minimal Anthropic-compatible Messages API client over the stdlib.

Single responsibility: send a one-shot prompt and return the text response.
Works against the public API or any proxy via ANTHROPIC_BASE_URL, and supports
both ``x-api-key`` and bearer ``auth-token`` credentials. Uses urllib so it has
no third-party dependency (the ``anthropic`` SDK is not assumed to be installed).
"""

import json
import os
import urllib.request

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


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
    def has_credentials() -> bool:
        """Whether the environment carries any usable credential."""
        return bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )

    @classmethod
    def from_env(cls, timeout=60) -> "AnthropicClient":
        """Build a client from ANTHROPIC_* environment variables."""
        return cls(
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
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
        return body["content"][0]["text"].strip()
