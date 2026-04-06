# feedback-loop

Monitors tool usage and failures, then helps refine permissions, rules, and memory based on real data.

## What It Does

Two hooks run silently in the background on every Claude session:

- **tool-detector** — logs every tool invocation to `~/.claude/feedback-loop/tool-detector.jsonl`
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
├── tool-detector.jsonl   # All tool invocations (rolling 3-month window)
└── fails.jsonl           # All tool failures (rolling 3-month window)
```

Entries older than 3 months are purged automatically on each hook run.

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
