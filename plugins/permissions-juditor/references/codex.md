# Codex classifier integration

The same custom classifier used in Claude runs for watched Codex PermissionRequest events. It calls the configured Anthropic-compatible API through AnthropicClient with the existing PERMISSIONS_JUDITOR_MODEL/EFFORT and credential configuration. It does not substitute Codex's native reviewer for this call.

Prompt policy comes from `$CLAUDE_CONFIG_DIR/settings.json` (default `~/.claude/settings.json`) for both hosts. Bash/MCP reference rules are filtered by call type; autoMode prose is shared. CODEX_HOME does not change that policy source. Native Codex rules/config remain the host's separate enforcement layer and are not scanned by this plugin.

Use AGENT_RUNTIME=codex, or allow PLUGIN_ROOT detection. The Codex manifest selects hooks/codex.json. The shared security-judge.py receives Bash or mcp__ tool inputs and returns:

- allow: PermissionRequest decision behavior=allow.
- deny: behavior=deny with the classifier reason.
- ask: no decision override, with systemMessage containing the reason. Codex does not support a PermissionRequest ask behavior.

Ask resumes the host's configured approval flow. If approvals_reviewer is auto_review, the host may send that fallback to its reviewer; select approvals_reviewer=user in native configuration when fallback must ask a human. This plugin does not silently change that setting. Missing credentials, malformed responses, and API failures return no override, never allow.

The hook only runs for requests that need approval, not every command. Codex sandbox/managed restrictions still apply. Decision logs use PLUGIN_DATA when supplied, otherwise `$CODEX_HOME/permissions-juditor` (default `~/.codex/permissions-juditor`). The main assistant model is independent of the classifier model. No live API call is made by unit tests.
