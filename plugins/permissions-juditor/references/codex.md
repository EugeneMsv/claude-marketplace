# Codex classifier integration

The same custom classifier used in Claude runs for watched Codex PermissionRequest events. It calls the configured Anthropic-compatible API through AnthropicClient with the existing PERMISSIONS_JUDITOR_MODEL/EFFORT and credential configuration. It does not substitute Codex's native reviewer for this call.

Prompt policy comes from `$CLAUDE_CONFIG_DIR/settings.json` (default `~/.claude/settings.json`) for both hosts. Bash/MCP reference rules are filtered by call type; autoMode prose is shared. CODEX_HOME does not change that policy source. Native Codex rules/config remain the host's separate enforcement layer and are not scanned by this plugin.

Use AGENT_RUNTIME=codex, or allow PLUGIN_ROOT detection. The Codex manifest selects hooks/codex.json. The shared security-judge.py receives Bash or mcp__ tool inputs and returns:

- allow: PermissionRequest decision behavior=allow.
- deny: behavior=deny with the classifier reason.
- ask: an empty object (`{}`), leaving the decision to the configured Codex approval reviewer.

Codex does not support a PermissionRequest ask behavior. Mapping ask to `{}` declines to decide: `approvals_reviewer = "user"` sends the request to the user, while `"auto_review"` sends eligible requests to the native reviewer. This does not change native approval settings. Claude continues to receive ask unchanged.

Missing credentials return no override. Malformed model responses and API failures on a watched call produce ask, which also returns `{}` under Codex. The configured reviewer therefore handles these failures and may approve or reject the action; the plugin itself does not auto-allow them. Claude receives the review request unchanged.

Decision logs preserve the classifier's original decision: an ask entry means the Codex adapter returned no decision, not a denial. Replaying a classifier input does not execute the classified command.

The hook only runs for requests that need approval, not every command. Codex sandbox/managed restrictions still apply. All projects append decisions to `$CODEX_HOME/permissions-juditor/decisions.jsonl` (default `~/.codex/permissions-juditor/decisions.jsonl`); `PLUGIN_DATA` does not override this location. Earlier plugin versions may have left logs in `PLUGIN_DATA`; those are not automatically migrated. The main assistant model is independent of the classifier model. No live API call is made by unit tests.
