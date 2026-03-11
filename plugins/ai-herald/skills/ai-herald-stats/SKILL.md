---
name: ai-herald-stats
description: >
  This skill should be used when the user invokes "/ai-herald-stats", or asks any of the following
  (or similar phrasing): "show AI attribution stats", "check AI contribution stats",
  "show current branch stats", "what is the AI percentage", "how much did AI contribute",
  "how many lines did Claude write", "what percentage of this branch is AI-generated",
  "show me the AI breakdown for this branch", "how much code did AI write so far",
  "what's my current AI attribution", "am I on track for AI contribution",
  "show AI vs human split", "check how much AI code is on this branch",
  or any request to see the current AI vs human contribution breakdown for the active branch
  without making a commit.
version: 0.1.0
---

# AI Herald Stats

Show AI vs human contribution statistics for the current branch on demand — without making a commit.

## Usage

Run the stats query script:

```bash
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-stats/herald-query-stats.py
```

For JSON output:

```bash
python3 $CLAUDE_PLUGIN_ROOT/skills/ai-herald-stats/herald-query-stats.py --json
```

## What It Shows

The script prints the current branch name and the same contribution breakdown that would be injected into the next commit message:

```
Branch: feature/my-feature
Overall: +120 -30
  AI: 100 lines (80.0%)
    +100 (83.3%)
    -0 (0.0%)
  Human: 25 lines (20.0%)
    +20 (16.7%)
    -5 (100.0%)
Tracked: .py, .ts
```

## Graceful Handling

The script exits cleanly with an informational message when:

- AI Herald is disabled in config
- Not in a git repository
- No tracking file exists for the current branch
- No merge base can be computed

## Presenting Results

After running the script, present the output to the user verbatim. If the output indicates no tracking data is available, explain that tracking begins when Claude writes or edits files on a feature branch and that stats appear once a commit has been made.
