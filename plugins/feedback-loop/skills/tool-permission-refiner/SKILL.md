---
name: msv-tool-permission-refiner
description: Audit logged tool usage against native permission settings and propose scoped changes. Use when the user asks to tool permission refiner or refine the corresponding agent behavior.
---

# Tool Permission Refiner

Use the current host to load exactly one procedure: [Codex](references/codex.md) or [Claude Code](references/claude.md). Do not apply another host's configuration format or infer that its memory paths exist.

Shared requirements:
- Base suggestions on actual conversation or hook-log evidence; separate observation from inference.
- Inspect existing instructions and policies for duplicates and conflicts.
- Present concise proposed changes, target files, and reasons before applying permission or policy changes.
- Honor the user's existing authorization; do not ask repeatedly for the same approved action.
- Never broaden approval rules simply because a command occurs frequently. Inspect arguments and side effects.
- Do not alter managed settings, credential stores, or internal memory databases.
- Verify edited files with the target platform's parser/checker and report limitations.
