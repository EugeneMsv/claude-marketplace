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

The tmux delivery path is a hard width constraint: two fixed status-format
rows that never wrap, so an overlong sentence gets truncated mid-word by tmux
itself with no ellipsis - worse than this hook's own bounded truncation.
`compute_sentence_char_budget` measures the pane's real window width before
calling the model and tells it the exact character limit to stay within, so
truncation (still enforced afterward as a backstop) should rarely trigger.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from anthropic_client import AnthropicClient

# JSONL trail of every decision this hook makes (fired, skipped and why, or
# errored) — mirrors grep-token-killer's audit log. Lets you confirm the hook
# is actually firing without needing a debugger on a subprocess Claude Code
# spawns per Bash call. Off by default (flip to True to debug firing issues).
DEBUG_LOG_ENABLED = False
DEBUG_LOG_PATH = Path.home() / ".claude" / "bash-brief" / "debug.jsonl"

# tmux 256-color palette for the window note - picked for readability against
# a dark status-bar background (colour236), spanning the hue wheel so a fresh
# random pick each time is visually obvious, not just a subtle shade change.
TMUX_NOTE_COLORS = (
    196, 202, 208, 214, 220, 226, 190, 154, 118, 82,
    46, 47, 48, 49, 50, 51, 45, 39, 33, 27,
    63, 99, 135, 165, 201, 207, 213, 219, 178, 172,
)

# Must match the fg= color the README's status-format[2]/[3] rows declare.
# tmux style codes have no "revert to previous style" - #[fg=X] just stays in
# effect until the next #[...], so after the randomly-colored prefix we must
# explicitly restate the row's own base color, not "default", or the tail of
# a sentence that spans onto line 2 (whose row re-declares this color itself)
# visibly mismatches the portion left on line 1. Keep this in sync if you
# change the row color in your own ~/.tmux.conf.
TMUX_NOTE_BASE_COLOR = 223

# Undated alias — the Claude API's own convenience pointer to the latest Haiku
# 4.5 snapshot. ANTHROPIC_DEFAULT_HAIKU_MODEL is Claude Code's own documented
# pinning variable for the Haiku-class model; reuse it if the environment
# already sets it (e.g. for Bedrock/Vertex deployments) instead of hardcoding
# a dated model id.
DEFAULT_MODEL = "claude-haiku-4-5"

MAX_COMMAND_CHARS = 4000

# Absolute ceiling regardless of the computed tmux budget below - a guard
# against an implausibly wide window producing an essay-length systemMessage.
MAX_SENTENCE_CHARS = 220

# Fallback sentence-length budget when not running inside tmux (systemMessage
# only, which wraps normally in the transcript) - keeps things skimmable even
# without a real width to measure against.
DEFAULT_SENTENCE_BUDGET = 160

# Each status-format row bakes in one leading and one trailing space (see the
# README's tmux.conf snippet) - subtract that per row before computing how
# much text actually fits across the two fixed rows.
TMUX_ROW_PADDING = 2

# MCP tool names are always "mcp__<server>__<tool>" (double underscore).
MCP_TOOL_PREFIX = "mcp__"

# Bounds how much of an MCP tool's raw JSON params get embedded in the prompt
# - unlike a Bash command string, MCP params can be arbitrarily large/free-form
# (SQL text, file contents, whole JSON blobs).
MAX_MCP_PARAMS_CHARS = 2000

PROMPT_TEMPLATE = """\
You are annotating a shell command or tool call for a software engineer who is about to \
approve it in an interactive terminal approval prompt. In EXACTLY one sentence, describe \
what it technically does — high-level, not a line-by-line trace.

Rules:
- Output ONLY the sentence. No preamble, no surrounding quotes, no markdown.
- Stay high-level: name the tool/action and its target, not implementation internals.
- Follow a source → filter/transform → destination chain, in that order.
- Name the source's origin explicitly (local file, network, stdin, etc.).
- State filter/match criteria concretely (exact counts or named targets), not vaguely.
- Name actual output fields or content when identifiable, not generic terms like "results".
- The full sentence must fit within {char_limit} characters — count carefully and stay \
at or under this limit, even if it means dropping detail.
- Do not judge or mention safety, risk, or whether to approve — a separate system \
already handles that.

Example command: cat response.json | jq '.status'
Example output: Reads a local JSON file and extracts the response status field.

Example command: python3 -c "import json; d=json.load(open('/tmp/disc.json')); \
[print(n['body']) for c in d for n in c.get('notes', []) if n['position']['new_line'] in (12, 132)]"
Example output: Reads a local JSON discussion file, matches entries against two specific \
line-number targets, and prints each match's comment body.

Example command: MCP tool `mcp__trino__execute_query` invoked with parameters: \
{{"query": "SELECT count(*) FROM orders LIMIT 10"}}
Example output: Runs a Trino SQL query via MCP to count rows in the orders table, limited to 10.

Input:
{command}
"""


def resolve_model(env=None) -> str:
    """Reuse Claude Code's own Haiku-pinning env var if set, else the undated alias."""
    env = env if env is not None else os.environ
    return env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", DEFAULT_MODEL)


def compute_sentence_char_budget(prefix: str, env=None) -> int:
    """How many characters the sentence may use, given where it will render.

    The tmux delivery path is a hard width constraint: the note fills exactly
    two fixed status-format rows that never wrap (see README), so overrunning
    them means tmux itself truncates mid-sentence with no ellipsis - the exact
    failure this exists to prevent. The budget is the pane's current window
    width, times two rows, minus each row's padding and the prefix tag, so
    the model is told the real limit instead of a guess. Falls back to
    DEFAULT_SENTENCE_BUDGET outside tmux, on a missing tmux binary, or on any
    subprocess/parse failure - never raises, matching every other tmux-facing
    function here.
    """
    env = env if env is not None else os.environ
    pane = env.get("TMUX_PANE")
    if not pane:
        return DEFAULT_SENTENCE_BUDGET
    try:
        width = int(
            subprocess.run(
                ["tmux", "display-message", "-p", "-t", pane, "#{window_width}"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            ).stdout.strip()
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        return DEFAULT_SENTENCE_BUDGET
    usable_per_row = width - TMUX_ROW_PADDING
    budget = usable_per_row * 2 - len(prefix) - 1  # -1: space between prefix and sentence
    return max(budget, DEFAULT_SENTENCE_BUDGET // 4)


def build_mcp_subject(tool_name: str, tool_input: dict) -> str:
    """Render an MCP tool call as text for the model to summarize.

    `tool_input` already came through json.loads() on hook stdin, so it's
    always JSON-serializable - no try/except needed. The slice below can cut
    mid-escape-sequence on an oversized value; harmless since this only feeds
    a prompt, never re-parsed as JSON.
    """
    params = json.dumps(tool_input, ensure_ascii=False)[:MAX_MCP_PARAMS_CHARS]
    return f"MCP tool `{tool_name}` invoked with parameters: {params}"


def summarize_command(client: AnthropicClient, command: str, char_limit: int) -> str:
    """Ask the model for a one-sentence technical description of the command or tool call.

    Parameter name predates MCP support - it now carries either a raw Bash
    command string or an MCP-call description built by build_mcp_subject().
    """
    truncated = command[:MAX_COMMAND_CHARS]
    return client.complete(
        model=resolve_model(),
        prompt=PROMPT_TEMPLATE.format(command=truncated, char_limit=char_limit),
        max_tokens=80,
    )


def clean_sentence(raw: str, char_limit: int) -> str:
    """Reduce a raw model response to a single, clean sentence within char_limit."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return ""

    sentence = lines[0].strip("\"' ")
    sentence = re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", sentence)
    if not sentence:
        return ""

    if len(sentence) > char_limit:
        cutoff = sentence.rfind(" ", 0, char_limit)
        cutoff = cutoff if cutoff > 0 else char_limit
        sentence = sentence[:cutoff].rstrip() + "…"
    elif sentence[-1] not in ".!?…":
        sentence += "."

    return sentence


def _now_stamp() -> str:
    """24-hour local time, no date - the message is a per-session running log."""
    return datetime.now().strftime("%H:%M:%S")


# Biases the two-line split past the midpoint so the first line - the one
# carrying the colored [bash-brief HH:MM:SS] tag - reads as the fuller line
# instead of looking clipped next to a longer second line.
TMUX_NOTE_FIRST_LINE_RATIO = 0.58


def split_into_two_lines(text: str, first_ratio: float = TMUX_NOTE_FIRST_LINE_RATIO) -> tuple[str, str]:
    """Split text into two lines at the nearest space to a biased split point.

    tmux status-format rows never wrap - each is exactly one physical line -
    so a fixed two-row layout needs the text pre-split, not relying on tmux
    to do it. Only ever splits at a space - never mid-word - so if there is
    no space anywhere in the text, everything stays on the first line and the
    second is empty rather than cutting a word in half. `first_ratio` > 0.5
    aims the split past the midpoint, toward a longer first line, rather than
    an even 50/50.
    """
    if not text:
        return "", ""
    target = int(len(text) * first_ratio)
    left = text.rfind(" ", 0, target + 1)
    right = text.find(" ", target)
    if left == -1 and right == -1:
        return text, ""
    elif left == -1:
        split_at = right
    elif right == -1:
        split_at = left
    else:
        split_at = left if (target - left) <= (right - target) else right
    return text[:split_at].rstrip(), text[split_at:].lstrip()


def set_tmux_window_note(prefix: str, sentence: str, env=None) -> None:
    """Write `prefix` + `sentence`, split across two lines, into this session's
    own tmux window options @bash_brief_note_1 / @bash_brief_note_2.

    Only `prefix` (the "[bash-brief HH:MM:SS]" tag) gets a freshly random
    color from TMUX_NOTE_COLORS each call, embedded as a tmux `#[fg=colourN]`
    style code directly in the option value, then reset to TMUX_NOTE_BASE_COLOR
    (matching the row's own base color, NOT tmux's "default") right after it -
    tmux style codes have no "revert to previous style"; resetting to
    "default" instead of the row's actual color visibly mismatched a sentence
    that spans onto line 2, since line 2's own row re-declares the base color
    itself. tmux parses style codes in a status-format string after
    substituting `#{@var}`, so this recolors just the tag on every update
    without touching ~/.tmux.conf or recoloring the sentence itself. The point
    is to draw the eye to the tag: a message that always looked the same
    would blend into a status bar you've stopped consciously reading.

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
    color = random.choice(TMUX_NOTE_COLORS)
    colored_prefix = f"#[fg=colour{color}]{prefix}#[fg=colour{TMUX_NOTE_BASE_COLOR}]"
    line1, line2 = split_into_two_lines(f"{colored_prefix} {sentence}")
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
    """Append one JSONL line when DEBUG_LOG_ENABLED; best-effort, swallows I/O errors."""
    if not DEBUG_LOG_ENABLED:
        return
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
    tool_input = hook_input.get("tool_input") or {}

    if tool_name == "Bash":
        subject = tool_input.get("command", "").strip()
    elif isinstance(tool_name, str) and tool_name.startswith(MCP_TOOL_PREFIX):
        subject = build_mcp_subject(tool_name, tool_input)
    else:
        subject = None

    base = {"tool_name": tool_name, "subject": (subject or "")[:200]}

    if subject is None:
        _debug_log({**base, "decision": "skip_unsupported_tool"})
        return {}
    if not subject:
        _debug_log({**base, "decision": "skip_empty_subject"})
        return {}

    if not AnthropicClient.has_credentials():
        _debug_log({**base, "decision": "skip_no_credentials"})
        return {}

    prefix = f"[bash-brief {_now_stamp()}]"
    char_limit = min(compute_sentence_char_budget(prefix), MAX_SENTENCE_CHARS)

    try:
        raw_response = summarize_command(AnthropicClient.from_env(), subject, char_limit)
        sentence = clean_sentence(raw_response, char_limit)
    except Exception as exc:  # noqa: BLE001
        _debug_log({**base, "decision": "skip_llm_error", "error": repr(exc)})
        return {}

    if not sentence:
        _debug_log({**base, "decision": "skip_empty_sentence", "raw_response": raw_response[:200]})
        return {}

    _debug_log({**base, "decision": "annotated", "sentence": sentence})
    set_tmux_window_note(prefix, sentence)
    return {"systemMessage": f"{prefix} {sentence}"}


def main() -> None:
    print(json.dumps(run(sys.stdin.read())))


if __name__ == "__main__":
    main()
