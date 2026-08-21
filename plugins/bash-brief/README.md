# bash-brief

Before a `Bash` call runs, adds a one-sentence, high-level technical description of what the command does — e.g. `[bash-brief 14:32:07] Reads a local JSON file and extracts the response status field.`

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `bash-command-summarizer` | PermissionRequest (`Bash`) | Calls a Haiku-class model with the command text and asks for exactly one non-judgmental, high-level technical sentence describing what it does. Prefixes it with `[bash-brief HH:MM:SS]` (24-hour local time, no date - the note is a running per-session log, see tmux Setup) and delivers it two ways: `systemMessage`, and (inside tmux) two window options read by your own `~/.tmux.conf`. |

### Why `PermissionRequest`, and why two delivery paths

An earlier version used `PreToolUse` for firing reliability (it fires before every Bash call regardless of permission mode). But `PreToolUse` fires far more broadly than what this hook is meant to describe — every Bash call, including ones that will never show any decision at all. `PermissionRequest` fires only when a real permission decision is actually needed, which is the exact moment this hook exists to annotate; a first attempt at it was gated on `permission_mode == "ask"`, a value that doesn't exist (real values are `default`, `plan`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions` — see [Claude Code hooks docs](https://code.claude.com/docs/en/hooks)), fixed by dropping the gate entirely. The tradeoff: in an auto-approving/auto-denying session, `PermissionRequest` — and this hook — may not fire at all, since no real decision was needed.

`systemMessage` itself was empirically confirmed (verified via a fixed dummy hook with zero other variables) to render only attached to the tool call's *completed* transcript entry — i.e. after you've already approved, never before or during the decision. There is no hook-level mechanism that reliably shows text before the decision: `hookSpecificOutput.additionalContext` is delivered to Claude's own context (a system reminder), not the user; `permissionDecisionReason` on an `"ask"` decision is documented to show pre-approval but is a currently-open, acknowledged Claude Code bug ([#17356](https://github.com/anthropics/claude-code/issues/17356)); the status line explicitly hides during permission prompts.

The one channel that *does* show up before/independent of the decision: a **tmux window option**, set directly via the `tmux` CLI talking to the tmux server's control socket (the same mechanism your own `~/.claude/tmux/tmux-claude-alert.sh` already uses for `@claude_alert`). It's tmux's own status-bar chrome, not anything Claude Code renders, so none of the above gating applies. See **tmux Setup** below.

Neither delivery path sets any permission decision field — this hook only surfaces a note, it never approves, denies, or otherwise gates the command; that responsibility stays with Claude Code's normal permission flow and other hooks (e.g. scope-control hooks).

## tmux Setup (optional, but the only pre-approval-visible path)

Requires running Claude Code inside tmux. tmux status-format rows never wrap, so the hook pre-splits the message at a word boundary (never mid-word) into `@bash_brief_note_1` / `@bash_brief_note_2` and drives two fixed status-bar rows. The split point is biased past the midpoint (`TMUX_NOTE_FIRST_LINE_RATIO`, default 0.58) so line 1 reads as the fuller line instead of looking clipped next to a longer line 2. Before calling the model, `compute_sentence_char_budget()` measures the pane's actual window width and tells the model the exact character limit to stay within — so the sentence is sized to fit the two rows instead of relying on tmux to truncate an overlong one mid-word.

```tmux
set -g status 4   # bump if you already set a lower row count
set -g status-format[2] '#[align=left,bg=colour236,fg=colour223] #{@bash_brief_note_1} '
set -g status-format[3] '#[align=left,bg=colour236,fg=colour223] #{@bash_brief_note_2} '
```

Then `tmux source-file ~/.tmux.conf` (or restart tmux) to apply it. Once set, the note is **never cleared automatically** — there is no hook event that reliably fires "after the human's decision" regardless of outcome (`PostToolUse` only fires on the allow-and-succeeded branch, never on a manual deny), so attempting partial cleanup would be inconsistent. The rows are a running log of the last Bash command's description, not a per-command popup.

The `[bash-brief HH:MM:SS]` tag (only the tag, not the sentence) also gets a freshly random foreground color from `TMUX_NOTE_COLORS` (30 tmux 256-color codes, embedded directly in the option value as `#[fg=colourN]...#[fg=colourM]` around just the tag) — the point is to draw the eye to a fresh update, since a message that always looked the same would blend into a status bar you've stopped consciously reading. The sentence itself always renders in the row's normal color.

**If you change the `fg=` color in your own status-format rows above, also update `TMUX_NOTE_BASE_COLOR` in `bash-command-summarizer.py` to match.** The reset after the tag targets that exact color, not tmux's "default" — a sentence long enough to span both lines has its tail (still on line 1) explicitly reset to this color, while line 2 re-declares its own `fg=` from the row format itself; if the two don't match, the two halves of one sentence visibly render in different colors.

Without tmux, or without this config, `bash-command-summarizer.py` silently skips the tmux write (checks `$TMUX_PANE`) and falls back to `systemMessage` only.

## Debug Logging

Off by default. `bash-command-summarizer.py`'s `DEBUG_LOG_ENABLED` constant gates a JSONL trail (`~/.claude/bash-brief/debug.jsonl`, one line per invocation: fired/skipped and why, or errored) — flip it to `True` to confirm the hook is actually firing without needing a debugger on a subprocess Claude Code spawns per Bash call.

## Model Resolution

Resolves the model in this order:

1. `ANTHROPIC_DEFAULT_HAIKU_MODEL` — Claude Code's own documented env var for pinning the Haiku-class model (useful on Amazon Bedrock/Google Vertex deployments where the bare alias may not be enabled).
2. `claude-haiku-4-5` — the Claude API's undated convenience alias for the latest Haiku 4.5 snapshot, used when the env var above is unset.

## Credential Resolution

This hook calls the public Messages API directly, so it needs a credential of its own — one that's separate from however you're logged into Claude Code. `anthropic_client.py` resolves it in this order:

1. `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` env vars, if either is set.
2. On macOS, the OAuth access token Claude Code itself stores in the login Keychain under the service name `Claude Code-credentials` (`claudeAiOauth.accessToken`) — used only if unexpired. This lets subscription/OAuth-authenticated users (no plain API key in their environment) get a working hook without exporting a separate credential. This is an internal storage detail of Claude Code, not a documented/stable API, so every step here fails silently back to "no credentials" rather than raising if the entry is missing, malformed, or the shape changes in a future Claude Code version.

If neither resolves, the hook silently no-ops (see Failure Handling below) rather than prompting for a key.

## Failure Handling

Missing credentials, network errors, malformed hook input, or an empty/unusable model response all fall through to a silent `{}` — the Bash call is never blocked or delayed by this hook failing (mirrors the `grep-token-killer` plugin's try/except safety net).

## Installation

```bash
claude plugin install bash-brief@eug-msv-claude-marketplace
```
