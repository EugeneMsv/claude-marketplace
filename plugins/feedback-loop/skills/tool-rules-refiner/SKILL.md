---
name: msv-tool-rules-refiner
description: This skill should be used when the user asks to "analyze tool failures", "learn from fail log", "improve tool rules", "update tools memory", "refine tool guidelines", "scan detection log", "extract tool learnings", or wants to derive rules from ~/.claude/feedback-loop/fails.jsonl into guides/Tools.md. Analyzes recurring failure patterns and proposes token-efficient one-liner rules grouped by tool and sub-command.
allowed-tools: Read, Grep, Glob, Bash
---

# Tool Rules Refiner

## Purpose

Analyze `~/.claude/feedback-loop/fails.jsonl` to extract failure patterns and propose structured rule additions or improvements to `~/.claude/guides/Tools.md`. Rules are one-liners grouped by tool and sub-command. Cross-references existing memory to avoid duplicates, conflicts, and redundancies.

## Target File

All output goes to `~/.claude/guides/Tools.md`. Never scatter rules into `CLAUDE.local.md` or other files unless explicitly asked.

## Core Workflow

### Phase 1: Parse Failures

```bash
jq -r '[.tool, .command, .error] | @tsv' ~/.claude/feedback-loop/fails.jsonl | sort
```

Group entries by:
- `tool` field (Bash, Read, Edit, Grep, Glob, etc.)
- Command sub-domain: extract the first token of `.command` for Bash (e.g., `git`, `gradle`, `jq`), or tool name for others

Count occurrences per error pattern. Failures appearing 2+ times are high-priority.

### Phase 2: Memory Audit

Read all memory files to cross-reference:
- `~/.claude/guides/Tools.md` — primary target
- `~/.claude/guides/Workflows.md` — git/workflow rules may already live here
- `~/.claude/CLAUDE.md` — global
- `~/.claude/CLAUDE.local.md` — global overrides
- `~/.claude/guides/Coding.md` — coding patterns
- `~/.claude/guides/*` — all other guides

**Check for:**
- Rule already exists → skip (no duplicate)
- Rule exists but same error recurs → mark as `STRENGTHEN` (improve the rule)
- Rule missing → mark as `ADD`
- Rule contradicts another file → mark as `CONFLICT`

### Phase 3: Generate Suggestions

See `references/format.md` for the target `Tools.md` structure and suggestion output format.

**Severity classification:**
- `STRENGTHEN` (🔴): Rule exists, failure repeated — current rule insufficient
- `ADD` (🟡): No rule, failure occurred 2+ times
- `CONFLICT` (⚠️): Proposed rule contradicts existing memory

**Rule quality criteria:**
- One line, imperative, action-first — prefer positive commands ("Use X", "Run Y before Z", "Stash before checkout")
- Reserve `NEVER` only for destructive or irreversible operations
- No examples unless critical (use inline: `Use X — not Y`)
- Minimal tokens: cut articles, use contractions, abbreviate obvious context
- If strengthening: replace old rule, don't add duplicate alongside it

### Phase 4: Present and Apply

Present suggestions grouped by severity: STRENGTHEN first, then ADD, then CONFLICT.

After user approval:
1. Apply changes to `guides/Tools.md`
2. If strengthening: replace the old weaker rule inline
3. Verify no duplicate lines exist after update
4. Confirm `guides/Tools.md` structure is intact

## Validation Checklist

Before presenting suggestions:
- ✓ Each rule backed by 2+ log entries (or 1 for STRENGTHEN)
- ✓ Rule not already present verbatim or semantically
- ✓ No contradiction with `Workflows.md` or `CLAUDE.local.md`
- ✓ Rule is a one-liner
- ✓ Grouped under correct tool section and sub-group
- ✓ STRENGTHEN cases show old rule vs. new rule diff

## Additional Resources

- **`references/format.md`** — Target `Tools.md` structure and suggestion output template
