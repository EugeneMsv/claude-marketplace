#!/usr/bin/env python3
"""PermissionRequest hook (Bash) — one-sentence technical summary of the pending command.

PermissionRequest fires only when a real permission decision is actually
needed - that's the exact moment this hook is meant to annotate, so no
permission_mode check is needed. This means it can skip entirely in
auto-approving/auto-denying sessions (a PreToolUse-based version was tried
for firing reliability instead, but PreToolUse fires before EVERY Bash call
regardless of whether a decision is even needed, which is broader than what
this hook is meant to describe).

Two delivery paths, since neither alone is reliable everywhere:
- `systemMessage`: the documented field, but confirmed (this session) to only
  render attached to the tool call's completed transcript entry - i.e. AFTER
  approval, never before or during the decision.
- A tmux window option (`@bash_brief_note`, read by a `status-format` row in
  the user's own ~/.tmux.conf - see README): confirmed to render immediately
  when the hook runs, before AND independent of the approval decision,
  because it's tmux's own status-bar chrome, not something Claude Code
  renders at all. Requires `$TMUX_PANE` to be set (running inside tmux) and
  the user's tmux.conf to have the matching status-format row; silently
  skipped otherwise. Never cleared once set (see README) - PostToolUse only
  fires on the allow-and-succeeded branch, never on a manual deny, so partial
  clearing would be inconsistent; it's left as a running last-command log.

Neither delivery sets hookSpecificOutput.additionalContext or any permission
decision - this hook only surfaces a note, it never gates or feeds Claude's
own context. A global try/except guarantees that on ANY failure (missing
credentials, network error, malformed stdin) the hook emits `{}` - the Bash
call must never be blocked or delayed by this hook failing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
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


def split_into_two_lines(text: str) -> tuple[str, str]:
    """Split text into two roughly-equal halves at the nearest space to the midpoint.

    tmux status-format rows never wrap - each is exactly one physical line -
    so a fixed two-row layout needs the text pre-split, not relying on tmux
    to do it. Only ever splits at a space - never mid-word - so if there is
    no space anywhere in the text, everything stays on the first line and the
    second is empty rather than cutting a word in half.
    """
    if not text:
        return "", ""
    midpoint = len(text) // 2
    left = text.rfind(" ", 0, midpoint + 1)
    right = text.find(" ", midpoint)
    if left == -1 and right == -1:
        return text, ""
    elif left == -1:
        split_at = right
    elif right == -1:
        split_at = left
    else:
        split_at = left if (midpoint - left) <= (right - midpoint) else right
    return text[:split_at].rstrip(), text[split_at:].lstrip()


def set_tmux_window_note(text: str, env=None) -> None:
    """Write `text`, split across two lines, into this session's own tmux window
    options @bash_brief_note_1 / @bash_brief_note_2.

    Requires $TMUX_PANE (set only when actually running inside tmux) and reads
    it fresh via `tmux display-message` rather than trusting a cached window
    id, since the pane can move between windows. Best-effort, never raises -
    a missing tmux binary, a pane outside tmux, or any subprocess failure just
    means the note isn't written.
    """
    env = env if env is not None else os.environ
    pane = env.get("TMUX_PANE")
    if not pane:
        return
    line1, line2 = split_into_two_lines(text)
    try:
        window = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{window_id}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
        if window:
            subprocess.run(
                ["tmux", "set-option", "-w", "-t", window, "@bash_brief_note_1", line1],
                timeout=3,
                check=False,
            )
            subprocess.run(
                ["tmux", "set-option", "-w", "-t", window, "@bash_brief_note_2", line2],
                timeout=3,
                check=False,
            )
    except (subprocess.SubprocessError, OSError):
        pass


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
    command = (hook_input.get("tool_input") or {}).get("command", "").strip()
    base = {"tool_name": tool_name, "command": command[:200]}

    if tool_name != "Bash":
        _debug_log({**base, "decision": "skip_not_bash"})
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
    message = f"🔎 [bash-brief] {sentence}"
    set_tmux_window_note(message)
    return {"systemMessage": message}


def main() -> None:
    print(json.dumps(run(sys.stdin.read())))


if __name__ == "__main__":
    main()
