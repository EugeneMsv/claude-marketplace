# bash-brief

Before Claude Code shows an approval prompt for a `Bash` call, adds a one-sentence, high-level technical description of what the command does — e.g. "Parses a JSON file to extract the response status field."

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `bash-command-summarizer` | PermissionRequest (`Bash`) | Calls a Haiku-class model with the command text and asks for exactly one non-judgmental, high-level technical sentence describing what it does. Emits it as a `systemMessage` alongside the approval prompt. `PermissionRequest` fires exactly when a tool call needs a permission decision — that IS the "about to ask" moment — so it adds no latency or cost for calls that never need a decision (auto-accepted, bypassed, etc.). |

### Why `PermissionRequest`, not `PreToolUse`

An earlier version of this hook used `PreToolUse` gated on `permission_mode == "ask"`. That value doesn't exist — real `permission_mode` values are `default`, `plan`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions` (see [Claude Code hooks docs](https://code.claude.com/docs/en/hooks)) — so the gate could never pass and the hook was a silent permanent no-op. `PermissionRequest` is the event purpose-built for this: it only fires when Claude Code is actually about to show the user a permission decision, and it carries the same `tool_name`/`tool_input` shape `PreToolUse` does.

## Design: Descriptive, Not Judgmental

This hook never sets `hookSpecificOutput.permissionDecision` — it only adds a `systemMessage`. It does not approve, deny, or otherwise gate the command; that responsibility stays with Claude Code's normal permission flow and other hooks (e.g. scope-control hooks). Its only job is to make the pending command easier to read at a glance.

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
