# feedback-loop

Monitors tool usage, prompts, and failures, then helps refine permissions, rules, and memory based on real data.

## What It Does

Three hooks run silently in the background on every Claude session:

- **tool-detector** — logs every tool invocation to `~/.claude/feedback-loop/tool-detector-YYYY-MM.jsonl`
- **prompt-detector** — logs every non-empty user prompt (prompt text, timestamp, session_id) to `~/.claude/feedback-loop/prompt-detector-YYYY-Www.jsonl`, for later prompt analysis. Always emits a bare `{}` — it's a pure side-effect logger and never injects context or interferes with other `UserPromptSubmit` hooks (e.g. `plan-guard`, `task-seeder`).
- **fail-detector** — logs every tool failure to `~/.claude/feedback-loop/fails.jsonl`

Three skills analyse those logs and propose targeted improvements:

| Skill | Trigger | Purpose |
|---|---|---|
| `tool-permission-refiner` | "audit tool permissions", "tighten permissions" | Reads `tool-detector.jsonl`, cross-references all permission layers, proposes allow/ask/deny changes |
| `tool-rules-refiner` | "analyze tool failures", "improve tool rules" | Reads `fails.jsonl`, proposes one-liner rules for `~/.claude/guides/Tools.md` |
| `memory-refiner` | "refine memory", "improve memory files" | Analyses conversation history, proposes improvements to `~/.claude/rules/*.md` and `CLAUDE.local.md` |

## Data Directory

All runtime data lives under `~/.claude/feedback-loop/`:

```
~/.claude/feedback-loop/
├── tool-detector-YYYY-MM.jsonl     # Tool invocations, one file per calendar month
├── prompt-detector-YYYY-Www.jsonl  # User prompts, one file per ISO week
└── fails.jsonl                     # Tool failures (rolling 3-month window)
```

Only `fails.jsonl` purges old entries automatically (on each hook run, anything older than 3 months is dropped). `tool-detector` and `prompt-detector` rotate into a fresh file each period instead — old files are kept as-is; delete them by hand if you want to reclaim space.

## Installation

```bash
claude plugin install feedback-loop@eug-msv-claude-marketplace
```

## Usage

Invoke any refiner skill naturally:

```
audit tool permissions
analyze tool failures
refine memory
```

Or via slash commands:

```
/tool-permission-refiner
/tool-rules-refiner
/memory-refiner
```

Each skill presents a numbered list of suggestions. You select which ones to apply.
