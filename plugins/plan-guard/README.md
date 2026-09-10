# plan-guard

Shared plugin for Claude Code and Codex. Set `AGENT_RUNTIME=claude|codex`; when unset, PLUGIN_ROOT selects Codex, otherwise Claude is selected. Python 3.11+ is required; plan snapshot locking targets Unix/macOS.

## Planning

The shared UserPromptSubmit hook runs only in `permission_mode=plan`. Claude retains its static/optional AI directives from `hooks/plan-guard/references/claude.md`; Codex gets native guidance from `references/codex.md` in the same directory without an extra API call. Guidance cannot switch the host mode or override user/system instructions.

The optional prompt-quality scorer is shared and still uses Anthropic when explicitly enabled with PLAN_GUARD_PROMPT_SCORER_ENABLED=1; installing in Codex does not switch that API provider. It is disabled by default in both hosts.

## Plan storage and cleanup

Claude retains its global-plan synchronization, metadata, and archive behavior. Codex persists explicit update_plan snapshots in `.Codex/plan-guard/plans/` under the hook cwd, indexed in PLUGIN_DATA or `$CODEX_HOME/plan-guard`. Full narrative plans without update_plan events are not automatically captured. Codex synchronization does not select the newest global plan or parse private transcript schemas.

The cleanup skill loads only the selected host reference. Its shared Python entry point routes to the appropriate archive implementation. Codex supports --dry-run, collision-safe dated archives, and symlink checks. It never edits Claude storage. Use the same runtime/data directory for capture and cleanup. Claude archival still moves global plans and associated project copies, then updates metadata and trims dated hook log entries; age now uses a precise day interval.

Codex plugin hooks require trust review before activation. The two manifests share the skill and hook entry points.

## Platform hook files

Each manifest selects a complete `hooks/claude.json` or `hooks/codex.json`. No default `hooks/hooks.json` is present. Both configurations invoke focused Python entry points directly, with host-specific events and root variables. Shared runtime helpers keep data paths separate.
