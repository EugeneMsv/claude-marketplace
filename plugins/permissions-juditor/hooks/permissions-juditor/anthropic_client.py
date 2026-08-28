#!/usr/bin/env python3
"""Minimal Anthropic-compatible Messages API client over the stdlib.

Single responsibility: send a one-shot prompt and return the text response.
Works against the public API or any proxy via ANTHROPIC_BASE_URL, and supports
both ``x-api-key`` and bearer ``auth-token`` credentials. Uses urllib so it has
no third-party dependency (the ``anthropic`` SDK is not assumed to be installed).

This file is the canonical, hand-maintained source — edit it directly. The
per-plugin copies under plugins/<name>/hooks/<name>/anthropic_client.py are
generated duplicates: never touch those directly. Instead, change this file
and run scripts/sync-shared-files.sh to propagate the change to every plugin
that vendors a copy.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"

# output_config.effort levels, highest spend first. Effort shapes every output
# token (text, tool arguments, and thinking), so on latency-sensitive hooks it
# is the single biggest lever available. "high" is the API default, so passing
# it is equivalent to omitting the key.
EFFORT_LEVELS = ("max", "xhigh", "high", "medium", "low")
DEFAULT_EFFORT = "medium"

# thinking.type values. "enabled" additionally requires budget_tokens and is
# rejected outright by 4.7+ models; "adaptive" is the form newer models want.
THINKING_TYPES = ("adaptive", "enabled", "disabled")

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


def _resolve_effort(effort: str | None) -> str | None:
    """Validate an effort level, or None to omit the key entirely.

    Rejects "adaptive" with a pointed message: it is a thinking *mode*, not an
    effort level, and passing it here is the natural mix-up once both knobs
    live on the same call.
    """
    if effort is None:
        return None
    if effort == "adaptive":
        raise ValueError(
            "'adaptive' is a thinking mode, not an effort level - pass "
            "thinking='adaptive' instead"
        )
    if effort not in EFFORT_LEVELS:
        raise ValueError(f"effort must be one of {EFFORT_LEVELS} or None, got {effort!r}")
    return effort


def _resolve_thinking(thinking: str | dict | None) -> dict | None:
    """Normalize the thinking config to a dict, or None to omit the key.

    A bare string is shorthand for {"type": <string>} so the common
    thinking="adaptive" case doesn't need a dict literal at every call site.
    """
    if thinking is None:
        return None
    if isinstance(thinking, str):
        thinking = {"type": thinking}
    thinking_type = thinking.get("type")
    if thinking_type not in THINKING_TYPES:
        raise ValueError(
            f"thinking type must be one of {THINKING_TYPES}, got {thinking_type!r}"
        )
    return thinking


def _apply_tuning(payload: dict, effort: str | None, thinking: dict | None) -> dict:
    """Merge effort/thinking into a payload, omitting either when None.

    effort nests under output_config, which may already carry other keys, so
    it merges into whatever is there rather than replacing the dict.
    """
    if effort is not None:
        payload.setdefault("output_config", {})["effort"] = effort
    if thinking is not None:
        payload["thinking"] = thinking
    return payload


def _apply_system(payload: dict, system: str | None, cache_system: bool) -> dict:
    """Set payload["system"] as a single text block, cache_control-marked when
    cache_system is set.

    A separate content-block array (rather than the plain-string form the
    system param also accepts) is required to attach cache_control at all -
    that field only exists on individual blocks. Ephemeral caching only pays
    off on a static prefix that's byte-identical across calls, so this is
    opt-in per call rather than automatic.
    """
    if system is None:
        return payload
    block = {"type": "text", "text": system}
    if cache_system:
        block["cache_control"] = {"type": "ephemeral"}
    payload["system"] = [block]
    return payload


def _has_tuning(payload: dict) -> bool:
    """Whether a payload carries thinking and/or output_config.effort - the
    two keys a 400-and-retry fallback knows how to strip."""
    return "thinking" in payload or "effort" in payload.get("output_config", {})


def _strip_tuning(payload: dict) -> dict:
    """Return a copy of payload with thinking and output_config.effort removed.

    Used as a one-shot retry body when the API rejects both keys outright -
    e.g. Haiku 4.5 and earlier, which support neither. Leaves any other
    output_config keys (like the structured-output schema) untouched.
    """
    stripped = {k: v for k, v in payload.items() if k != "thinking"}
    output_config = {k: v for k, v in stripped.get("output_config", {}).items() if k != "effort"}
    if output_config:
        stripped["output_config"] = output_config
    else:
        stripped.pop("output_config", None)
    return stripped


def _rejects_tuning(http_error_body: str) -> bool:
    """Whether a 400 response body's error message names thinking or
    output_config/effort as the offending field - the model-doesn't-support-this
    case this fallback exists for, as opposed to an unrelated 400 (bad schema,
    bad model id) that stripping tuning keys wouldn't fix."""
    try:
        message = json.loads(http_error_body).get("error", {}).get("message", "")
    except json.JSONDecodeError:
        message = http_error_body
    message = message.lower()
    return any(term in message for term in ("thinking", "output_config", "effort"))


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
        """Return (api_key, auth_token, base_url_override).

        Resolution order:
        1. HOOKS_LLM_URL + HOOKS_LLM_AUTH_TOKEN, both required together (an
           unset or empty value on either side means neither is used, falling
           through to the next tier). This is an explicit, portable
           configuration a user sets themselves - e.g. via a Claude Code
           settings.json "env" block - naming exactly which endpoint and
           credential hooks should use. It takes priority over everything
           else precisely because it's explicit rather than discovered.
        2. ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN env vars, if either is set.
        3. On macOS, the OAuth access token Claude Code itself stores in the
           login Keychain - a fallback for subscription/OAuth-authenticated
           users who haven't configured either of the above.
        """
        hooks_llm_url = os.environ.get("HOOKS_LLM_URL")
        hooks_llm_auth_token = os.environ.get("HOOKS_LLM_AUTH_TOKEN")
        if hooks_llm_url and hooks_llm_auth_token:
            return None, hooks_llm_auth_token, hooks_llm_url

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if api_key or auth_token:
            return api_key, auth_token, None

        return None, _read_macos_keychain_oauth_token(), None

    @staticmethod
    def has_credentials() -> bool:
        """Whether any usable credential (HOOKS_LLM_*, ANTHROPIC_* env var, or
        Keychain fallback) is available."""
        api_key, auth_token, _ = AnthropicClient._resolve_credentials()
        return bool(api_key or auth_token)

    @classmethod
    def from_env(cls, timeout=60) -> "AnthropicClient":
        """Build a client from HOOKS_LLM_*/ANTHROPIC_* environment variables,
        falling back to the macOS Keychain OAuth token when none are set.

        A HOOKS_LLM_URL override takes the base_url slot outright (ignoring
        ANTHROPIC_BASE_URL) since it only ever resolves paired with
        HOOKS_LLM_AUTH_TOKEN - the two travel together as one explicit
        endpoint+credential configuration, not independent settings.
        """
        api_key, auth_token, base_url_override = cls._resolve_credentials()
        return cls(
            base_url=base_url_override or os.environ.get("ANTHROPIC_BASE_URL"),
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

    def _send(self, payload: dict) -> dict:
        """POST a single payload to /v1/messages and return the decoded body."""
        request = urllib.request.Request(
            f"{self._base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _post(self, payload: dict) -> dict:
        """POST a payload to /v1/messages, retrying once without thinking/effort
        if the model rejects them outright.

        Every caller of this client fails open on exception (per-plugin
        hooks catch broadly and fall through to "no override"), so an
        unretried 400 from an unsupported model - e.g. Haiku 4.5, which has
        no effort support at all - is a silent no-op rather than a visible
        error. This fallback is deliberately narrow: it only fires when the
        payload actually carries thinking/effort and the error message names
        one of them, so an unrelated 400 (bad schema, bad model id) still
        propagates immediately instead of masking the real cause behind a
        pointless retry.
        """
        if not _has_tuning(payload):
            return self._send(payload)
        try:
            return self._send(payload)
        except urllib.error.HTTPError as error:
            if error.code != 400:
                raise
            body_text = error.read().decode("utf-8")
            if not _rejects_tuning(body_text):
                raise
            return self._send(_strip_tuning(payload))

    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        effort: str | None = DEFAULT_EFFORT,
        thinking: str | dict | None = None,
        system: str | None = None,
        cache_system: bool = False,
    ) -> str:
        """Send a single user message and return the first text block, stripped.

        effort defaults to "medium" rather than the API's "high": these callers
        are hooks on the interactive path, where latency costs more than the
        last increment of quality. Pass effort=None to omit the key - required
        for models that don't support it at all (Haiku 4.5 and earlier), which
        reject the request with HTTP 400.

        system splits a static prefix out of the user message; set
        cache_system=True to mark it for prompt caching when that prefix is
        byte-identical across repeated calls (e.g. instructions plus reference
        data that doesn't change within a session) - below the model's minimum
        cacheable length (1,024 tokens on current Sonnet models), the API
        accepts the marker but never actually caches, silently.
        """
        payload = _apply_system(
            _apply_tuning(
                {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                _resolve_effort(effort),
                _resolve_thinking(thinking),
            ),
            system,
            cache_system,
        )
        body = self._post(payload)
        # Some models prepend a "thinking" block — find the first text block instead
        # of assuming content[0] is text.
        for block in body["content"]:
            if block.get("type") == "text":
                return block["text"].strip()
        return ""

    def complete_with_tool(
        self,
        model: str,
        prompt: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        max_tokens: int,
        effort: str | None = DEFAULT_EFFORT,
        thinking: str | dict | None = None,
        system: str | None = None,
        cache_system: bool = False,
    ) -> dict:
        """Send a single user message with a forced tool call and return the tool's
        parsed input dict.

        Uses tool_choice to force the model to call exactly this tool, and
        "strict": true so its arguments are constrained to conform to
        input_schema by construction - this is what makes the result safe to
        branch on programmatically without fragile free-text parsing.

        The API rejects a strict object schema with HTTP 400 unless
        "additionalProperties": false is set explicitly - a non-obvious
        requirement callers would otherwise discover only via that error, so
        it's defaulted here (via setdefault, on a copy - the caller's dict is
        never mutated) rather than left as tribal knowledge every caller must
        remember. An explicit value already present in input_schema wins.

        thinking is constrained here in a way it isn't on complete(): manual
        extended thinking (type "enabled") is incompatible with a tool_choice
        that forces tool use, and the API returns an error. Adaptive thinking
        supports forced tool use, so it's the only mode allowed through.

        See complete()'s docstring for system/cache_system.
        """
        resolved_thinking = _resolve_thinking(thinking)
        if resolved_thinking is not None and resolved_thinking["type"] == "enabled":
            raise ValueError(
                "thinking type 'enabled' is incompatible with forced tool_choice - "
                "use 'adaptive' instead"
            )
        schema = {**input_schema, "additionalProperties": input_schema.get("additionalProperties", False)}
        payload = _apply_system(
            _apply_tuning(
                {
                    "model": model,
                    "max_tokens": max_tokens,
                    "tools": [
                        {
                            "name": tool_name,
                            "description": tool_description,
                            "input_schema": schema,
                            "strict": True,
                        }
                    ],
                    "tool_choice": {"type": "tool", "name": tool_name},
                    "messages": [{"role": "user", "content": prompt}],
                },
                _resolve_effort(effort),
                resolved_thinking,
            ),
            system,
            cache_system,
        )
        body = self._post(payload)
        for block in body["content"]:
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                return block["input"]
        raise ValueError(f"no tool_use block found for tool {tool_name!r} in response")
