# plan-guard

Enforces plan mode discipline, syncs plan files to project directories, and helps clean up old plans.

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `plan-mode-enforcer` | UserPromptSubmit | Injects project-specific planning requirements at the start of each prompt in plan mode. Uses the Anthropic API to generate requirements from `CLAUDE.md` + `key-commands.md`; falls back to sensible defaults if no context found. |
| `copy-plan-on-change` | PostToolUse (Write/Edit) | Syncs any plan file edited under `~/.claude/plans/` to the current project's `.claude/plans/` directory. Associates plan names to project paths via `~/.claude/plans/.metadata`. |
| `copy-plan-on-exit` | PostToolUse (ExitPlanMode) | Performs a final sync of the most recent plan file when plan mode exits. |

### Skills

| Skill | Trigger | Purpose |
|---|---|---|
| `cleanup-plans` | "cleanup old plans", `/cleanup-plans [age]` | Deletes global and project-specific plan files older than the specified age (default: `2w`). Cleans metadata entries and `hook.log` lines. |

## Plan Sync Behavior

- Plans are always synced to the **git repository root** (not the subdirectory Claude was started from)
- Cross-session isolation: a plan registered for Project A will not sync to Project B
- Plan-to-project associations are stored in `~/.claude/plans/.metadata` (line format: `plan-name.md:/absolute/path`)

## Plan Mode Enforcer

On each user prompt in plan mode, the hook:

1. Detects build tools in the project (`build.gradle`, `pom.xml`, `package.json`, etc.)
2. Reads `CLAUDE.md` and `key-commands.md` for context
3. Calls `claude-haiku` to produce a concise planning requirements message
4. Falls back to standard defaults if the API call fails

Override the model via `ANTHROPIC_MODEL` env var.

## Installation

```bash
claude plugin install plan-guard@eug-msv-claude-marketplace
```

## Debugging

Hook activity is logged to `~/.claude/logs/hook.log`.

```bash
# Follow live
tail -f ~/.claude/logs/hook.log

# Enable verbose output
export CLAUDE_HOOK_LOG_LEVEL=debug
```

See `hooks/plan-guard/TROUBLESHOOTING.md` for a full debugging guide.
