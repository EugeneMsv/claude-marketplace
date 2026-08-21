# bash-brief

Before Claude Code shows an approval prompt for a `Bash` call, adds a one-sentence, high-level technical description of what the command does — e.g. "Parses a JSON file to extract the response status field."

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `bash-command-summarizer` | PreToolUse (`Bash`) | Calls a Haiku-class model with the command text and asks for exactly one non-judgmental, high-level technical sentence describing what it does. Emits it as a `systemMessage` alongside the approval prompt. Fires only when `permission_mode == "ask"` — i.e. only when Claude Code is actually about to prompt for approval — so it adds no latency or cost when a command would run without a prompt anyway. |

## Design: Descriptive, Not Judgmental

This hook never sets `hookSpecificOutput.permissionDecision` — it only adds a `systemMessage`. It does not approve, deny, or otherwise gate the command; that responsibility stays with Claude Code's normal permission flow and other hooks (e.g. scope-control hooks). Its only job is to make the pending command easier to read at a glance.

## Model Resolution

Resolves the model in this order:

1. `ANTHROPIC_DEFAULT_HAIKU_MODEL` — Claude Code's own documented env var for pinning the Haiku-class model (useful on Amazon Bedrock/Google Vertex deployments where the bare alias may not be enabled).
2. `claude-haiku-4-5` — the Claude API's undated convenience alias for the latest Haiku 4.5 snapshot, used when the env var above is unset.

## Failure Handling

Missing credentials, network errors, malformed hook input, or an empty/unusable model response all fall through to a silent `{}` — the Bash call is never blocked or delayed by this hook failing (mirrors the `grep-token-killer` plugin's try/except safety net).

## Installation

```bash
claude plugin install bash-brief@eug-msv-claude-marketplace
```
