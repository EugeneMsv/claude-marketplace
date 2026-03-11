---
name: ai-herald-history
description: >
  This skill should be used when the user invokes "/ai-herald-history", or asks any of the following
  (or similar phrasing): "show AI history", "show historical AI stats", "AI trend",
  "how has AI usage changed over time", "show AI contribution history",
  "what is the AI trend over the last month", "show weekly AI breakdown",
  "has AI usage been increasing", "show AI percentage by week",
  "how much AI code was written this month", "give me the historical AI attribution report",
  "show AI contribution over time", "what does the AI adoption curve look like",
  or any request to view historical AI vs human contribution trends across past commits.
version: 0.1.0
---

# AI Herald History

Query historical AI contribution stats across past commits, grouped by week, month, or individual commit.

## Prerequisites

History tracking must be enabled in `~/.claude/ai-herald/config.json`:

```json
"history": {
  "enabled": true
}
```

Once enabled, each new commit will append a record to the history store.

## Usage

```bash
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-history/herald-history.py
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--by week\|month\|commit` | `week` | Grouping period |
| `--since 30d\|4w\|3m\|YYYY-MM-DD` | (all time) | Filter by date |
| `--author EMAIL` | (all authors) | Filter by author email |
| `--format table\|json\|csv` | `table` | Output format |
| `--json` | — | Shorthand for `--format=json` |

### Examples

```bash
# Last 8 weeks, grouped by week (default)
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-history/herald-history.py --since 8w

# Monthly breakdown for the year
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-history/herald-history.py --by month --since 2026-01-01

# Per-commit view for one author
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-history/herald-history.py --by commit --author alice@example.com

# JSON output for scripting
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-history/herald-history.py --json
```

## Sample Output

```
AI Contribution History — github.com_alice_my-repo

Week         Commits  AI%    Added                   Removed               Ignored
-----------  -------  -----  ----------------------  --------------------  -------
2026-01-12   3        45%    +180 / +99 AI           -40 / -12 AI          0 lines
2026-01-19   5        58%    +310 / +180 AI          -55 / -28 AI          8 lines (**/generated/**)
2026-01-26   8        71%    +420 / +298 AI          -80 / -51 AI          0 lines

Trend: ▲ +26pp over 3 weeks  |  Total: 16 commits  |  Avg AI%: 58%
```

## Presenting Results

After running the script, present the output verbatim. If the output explains that history is not enabled, show the user the config snippet and explain they need to opt in before history begins accumulating.
