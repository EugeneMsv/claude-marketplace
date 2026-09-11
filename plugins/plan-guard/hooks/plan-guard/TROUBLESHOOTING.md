# Plan Guard troubleshooting

## Select the runtime

Use `AGENT_RUNTIME=claude` or `AGENT_RUNTIME=codex`. If unset, PLUGIN_ROOT selects Codex; otherwise Claude is selected. Verify the manifest points to the corresponding complete hooks/claude.json or hooks/codex.json. Review/trust Codex hooks before activation.

## Entry points

- plan-mode-enforcer.py: loads planning guidance when permission_mode is plan.
- plan-sync.py: Claude Write/Edit/ExitPlanMode handling or Codex update_plan snapshots.
- ../../skills/cleanup-plans/scripts/archive-plans.py: recoverable cleanup with optional --dry-run.
- plan_storage.py: shared locking, file writes, metadata, and archive functions; not a command entry point.

## Claude plans

Inspect `$CLAUDE_CONFIG_DIR/plans/.metadata` (default ~/.claude/plans/.metadata). Entries are `plan-name.md:/absolute/project/path`. A plan assigned to another project is not copied into the current project. Git working directories are normalized to their repository root. ExitPlanMode keeps the legacy newest-global-plan selection; explicit file events are more precise. Global configuration cwd requires an existing project association.

Source plans must be top-level Markdown files in the selected global plans directory. Project copies use `.claude/plans/`. Symlink destinations are rejected. Legacy plan-projects.json associations can be read; saving an association writes .metadata without deleting the old JSON.

## Codex plans

Only explicit successful update_plan events are saved. Narrative plans without that event are not captured. Snapshots live under the hook cwd in `.Codex/plan-guard/plans/`; the project index is in PLUGIN_DATA or `$CODEX_HOME/plan-guard`. Capture and cleanup must use the same runtime/data directory.

## Errors and validation

The synchronization hook reports an error type on stderr and returns `{}` to preserve the host's flow. It does not retain the removed shell scripts' debug log messages or CLAUDE_HOOK_LOG_LEVEL handling. Inspect hook diagnostics in the host. Cleanup prints selected/archive paths and reports errors with a nonzero exit code.

Run the Python entry points directly; there are no shell wrappers. Validate the plugin manifests and run the regression tests before activation. Never debug synchronization against production projects or by modifying real plans without authorization.
