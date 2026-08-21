#!/usr/bin/env python3
"""PreToolUse hook (Bash) — one-sentence technical summary shown before the approval prompt.

Fires only when Claude Code is actually about to ask for approval
(permission_mode == "ask"); in any other mode this is a silent no-op so it never
adds latency or API cost when a command would run without a prompt anyway. A
global try/except guarantees that on ANY failure (missing credentials, network
error, malformed stdin) the hook emits `{}` — the Bash call must never be
blocked or delayed by this hook failing.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from anthropic_client import AnthropicClient

# Always-on JSONL trail of every decision this hook makes (fired, skipped and
# why, or errored) — mirrors grep-token-killer's audit log. Lets you confirm
# the hook is actually firing without needing a debugger on a subprocess
# Claude Code spawns per Bash call.
DEBUG_LOG_PATH = Path.home() / ".claude" / "bash-brief" / "debug.jsonl"

# Undated alias — the Claude API's own convenience pointer to the latest Haiku
# 4.5 snapshot. ANTHROPIC_DEFAULT_HAIKU_MODEL is Claude Code's own documented
# pinning variable for the Haiku-class model; reuse it if the environment
# already sets it (e.g. for Bedrock/Vertex deployments) instead of hardcoding
# a dated model id.
DEFAULT_MODEL = "claude-haiku-4-5"

MAX_COMMAND_CHARS = 4000
MAX_SENTENCE_CHARS = 220

PROMPT_TEMPLATE = """\
You are annotating a shell command for a software engineer who is about to approve it \
in an interactive terminal approval prompt. In EXACTLY one sentence, describe what the \
command technically does — high-level, not a line-by-line trace.

Rules:
- Output ONLY the sentence. No preamble, no surrounding quotes, no markdown.
- Stay high-level: name the tool/action and its target, not implementation internals.
- Do not judge or mention safety, risk, or whether to approve — a separate system \
already handles that.

Example command: cat response.json | jq '.status'
Example output: Parses a JSON file to extract the response status field.

Command:
{command}
"""


def resolve_model(env=None) -> str:
    """Reuse Claude Code's own Haiku-pinning env var if set, else the undated alias."""
    env = env if env is not None else os.environ
    return env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", DEFAULT_MODEL)


def summarize_command(client: AnthropicClient, command: str) -> str:
    """Ask the model for a one-sentence technical description of the command."""
    truncated = command[:MAX_COMMAND_CHARS]
    return client.complete(
        model=resolve_model(),
        prompt=PROMPT_TEMPLATE.format(command=truncated),
        max_tokens=80,
    )


def clean_sentence(raw: str) -> str:
    """Reduce a raw model response to a single, clean, bounded-length sentence."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return ""

    sentence = lines[0].strip("\"' ")
    sentence = re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", sentence)
    if not sentence:
        return ""

    if len(sentence) > MAX_SENTENCE_CHARS:
        cutoff = sentence.rfind(" ", 0, MAX_SENTENCE_CHARS)
        cutoff = cutoff if cutoff > 0 else MAX_SENTENCE_CHARS
        sentence = sentence[:cutoff].rstrip() + "…"
    elif sentence[-1] not in ".!?…":
        sentence += "."

    return sentence


def _debug_log(record: dict) -> None:
    """Append one JSONL line; best-effort, swallows I/O errors."""
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **record}, ensure_ascii=False)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except (OSError, TypeError, ValueError):
        pass


def run(raw_input: str) -> dict:
    """Return the response dict to print ({} = no annotation). Never raises."""
    try:
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, TypeError):
        _debug_log({"decision": "skip_malformed_json"})
        return {}

    tool_name = hook_input.get("tool_name")
    permission_mode = hook_input.get("permission_mode")
    command = (hook_input.get("tool_input") or {}).get("command", "").strip()
    base = {"tool_name": tool_name, "permission_mode": permission_mode, "command": command[:200]}

    if tool_name != "Bash":
        _debug_log({**base, "decision": "skip_not_bash"})
        return {}
    if permission_mode != "ask":
        _debug_log({**base, "decision": "skip_permission_mode_not_ask"})
        return {}
    if not command:
        _debug_log({**base, "decision": "skip_empty_command"})
        return {}

    if not AnthropicClient.has_credentials():
        _debug_log({**base, "decision": "skip_no_credentials"})
        return {}

    try:
        raw_response = summarize_command(AnthropicClient.from_env(), command)
        sentence = clean_sentence(raw_response)
    except Exception as exc:  # noqa: BLE001
        _debug_log({**base, "decision": "skip_llm_error", "error": repr(exc)})
        return {}

    if not sentence:
        _debug_log({**base, "decision": "skip_empty_sentence", "raw_response": raw_response[:200]})
        return {}

    _debug_log({**base, "decision": "annotated", "sentence": sentence})
    return {"systemMessage": f"[bash-brief] {sentence}"}


def main() -> None:
    print(json.dumps(run(sys.stdin.read())))


if __name__ == "__main__":
    main()
