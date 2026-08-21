# bash-brief

Before a `Bash` call runs, adds a one-sentence, high-level technical description of what the command does — e.g. "Parses a JSON file to extract the response status field."

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `bash-command-summarizer` | PreToolUse (`Bash`) | Calls a Haiku-class model with the command text and asks for exactly one non-judgmental, high-level technical sentence describing what it does. Emits it as a `systemMessage`. |

### Why `PreToolUse`, and why it's the only field set

Two earlier designs were tried and dropped:

- A `PermissionRequest` hook gated on `permission_mode == "ask"`. That value doesn't exist — real `permission_mode` values are `default`, `plan`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions` (see [Claude Code hooks docs](https://code.claude.com/docs/en/hooks)) — so the gate never passed.
- After fixing that, a `PermissionRequest` hook emitting only `systemMessage`. `PermissionRequest` only fires when a real permission decision is actually needed, which auto-approving/auto-denying sessions can skip entirely — so it fired inconsistently depending on session permission mode.

`PreToolUse` fires before every Bash call regardless of permission mode, so it's the reliable choice. The hook sets `systemMessage` only — never `hookSpecificOutput.additionalContext` (which is delivered to Claude's own context as a system reminder, not to the user) and never any permission decision field. It does not approve, deny, or otherwise gate the command; that responsibility stays with Claude Code's normal permission flow and other hooks (e.g. scope-control hooks). Its only job is to make the pending command easier to read at a glance.

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
