# task-seeder

Reminds the agent that a prompt covering more than one thing may be worth splitting into a `Task N: ...` breakdown via `TaskCreate`, especially when part of the ask needs exploration/research before implementation.

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `task-breakdown-drafter` | UserPromptSubmit | Injects a fixed, non-binding reminder as `additionalContext` on every non-empty prompt outside plan mode: consider splitting multi-part asks into tasks, check `TaskList` first for existing overlapping tasks, and prefer adding as a subtask over spawning a conflicting parallel task tree. Purely static — no model call, no heuristic gating on the prompt's content. The decision of whether splitting actually applies is left entirely to the agent handling the prompt. |

## Design: Static, Not AI-Judged

This hook does **not** call any LLM API and does not depend on `anthropic_client.py` or any credential. It emits the same fixed reminder text every time it fires — the reminder itself says "may or may not apply here" and leaves the actual judgment call to whichever agent receives it. This keeps the hook instant (no network round trip) and removes any API-cost or availability concern from firing on every prompt.

## Plan Mode Exclusion

This hook is a complete no-op whenever `permission_mode == "plan"` — that mode is already fully owned by the `plan-guard` plugin's own `UserPromptSubmit` hooks (`plan-mode-enforcer`, `prompt-quality-scorer`), which enforce a mandatory task breakdown as part of formal planning. `task-breakdown-drafter` checks this before anything else, so the two plugins never compete or duplicate signal.

## Status Message

On every successful injection, the hook prints a `systemMessage` naming its own plugin version (read from `plugin.json` at runtime), e.g. `[task-seeder v0.1.0] Task-split reminder applied.` — so it's visible when the reminder fired and which plugin version produced it.

## Installation

```bash
claude plugin install task-seeder@eug-msv-claude-marketplace
```
