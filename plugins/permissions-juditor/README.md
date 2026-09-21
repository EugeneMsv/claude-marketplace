# permissions-juditor

Claude Code and Codex use the same custom Anthropic classifier, prompt templates, watched-command/MCP scope, model selection, and effort settings.

## Single prompt-policy source

Both runtimes read `$CLAUDE_CONFIG_DIR/settings.json`, defaulting to `~/.claude/settings.json`. The selected runtime does not change this source. `permissions.allow/ask/deny` supplies reference rules; `autoMode.environment/allow/soft_deny/hard_deny` supplies prose guidance. These values build the classifier prompt; they are not imported into Codex native permissions. Settings are reread for each classified request. A separate policy source can be introduced later through the existing centralized loader.

## Runtime adapters

Set `AGENT_RUNTIME=claude|codex`. If unset, PLUGIN_ROOT selects Codex; otherwise Claude is selected. Each manifest selects its complete hooks/claude.json or hooks/codex.json, both calling security-judge.py directly.

- [Claude Code](references/claude.md): classifier decisions map to Claude PermissionRequest outputs.
- [Codex](references/codex.md): the same classifier runs; allow/deny map to Codex outputs, while ask maps to deny with an explanation. Logs preserve the original classifier decision.

Errors or missing credentials never auto-allow. All projects share `decisions.jsonl` under `$CODEX_HOME/permissions-juditor` (default `~/.codex/permissions-juditor`) or `$CLAUDE_CONFIG_DIR/permissions-juditor` (default `~/.claude/permissions-juditor`); `PLUGIN_DATA` does not override this location. Policy stays shared. Review and trust Codex hooks before use. Installation does not change native approval settings.

If decision logs appear missing after an update, check the shared runtime directory above. Earlier Codex versions of this plugin could write to `PLUGIN_DATA`; existing logs there are left in place and are not automatically merged.
