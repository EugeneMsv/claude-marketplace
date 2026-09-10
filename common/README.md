# Shared plugin code

## Dual runtime support

`agent_runtime.py` is canonical and vendored into each consuming plugin because installed plugin archives cannot import sibling directories. The existing `scripts/sync-shared-files.sh` keeps those copies synchronized.

`AGENT_RUNTIME=claude|codex` explicitly selects the integration. Without it, `PLUGIN_ROOT` identifies Codex; otherwise Claude is the default. Do not detect Codex from `CLAUDE_PLUGIN_ROOT`, because Codex exports that compatibility variable too. Invalid explicit values are errors, never guessed modes.

For Claude, configure the variable in settings.json's env object. For Codex, configure it under `[shell_environment_policy.set]` in config.toml. In plugin hooks, prefer host detection unless testing or invoking a script manually. The main assistant's model is independent of this selector.

State paths honor CODEX_HOME or CLAUDE_CONFIG_DIR. Codex logging/index files prefer PLUGIN_DATA when supplied by the host. Skills load the matching runtime reference and must locate the actual plugin data directory rather than assume a cache path. Python 3.11+ and Unix/macOS file locking are required by the new adapters.

Both plugin manifests point to shared source. Each hook-bearing migrated plugin has complete `hooks/claude.json` and `hooks/codex.json` configurations selected explicitly by its manifests. Python entry points own individual jobs, with shared helpers named for their responsibilities. Code Sentinel is skills-only and does not need hook configurations. Do not auto-trust hooks or install global permission changes during plugin installation.
