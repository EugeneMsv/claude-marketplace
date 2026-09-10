---
name: msv-cleanup-plans
description: Archive old plan files without deleting them. Use when asked to clean up plans, remove old plans, or archive plans older than a given age.
---

# Cleanup plans

Read exactly one runtime reference: [Codex](references/codex.md) or [Claude Code](references/claude.md).

- Honor the host's actual plan locations and the selected runtime.
- Accept an age such as 2w, 30d, or 1m; default to 2w.
- Archive by moving into a dated folder in the same plan directory. Never hard-delete or overwrite a plan.
- Inspect the candidate set and respect the user's authorization before applying.
- Use the bundled script resolved from this skill's directory, setting `AGENT_RUNTIME=codex` or `AGENT_RUNTIME=claude` explicitly.
- Verify archived content exists and report source/destination counts and failures.
