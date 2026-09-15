# Codex classifier integration

The same custom classifier used in Claude runs for watched Codex PermissionRequest events. It calls the configured Anthropic-compatible API through AnthropicClient with the existing PERMISSIONS_JUDITOR_MODEL/EFFORT and credential configuration. It does not substitute Codex's native reviewer for this call.

Prompt policy comes from `$CLAUDE_CONFIG_DIR/settings.json` (default `~/.claude/settings.json`) for both hosts. Bash/MCP reference rules are filtered by call type; autoMode prose is shared. CODEX_HOME does not change that policy source. Native Codex rules/config remain the host's separate enforcement layer and are not scanned by this plugin.

Use AGENT_RUNTIME=codex, or allow PLUGIN_ROOT detection. The Codex manifest selects hooks/codex.json. The shared security-judge.py receives Bash or mcp__ tool inputs and returns:

- allow: PermissionRequest decision behavior=allow.
- deny: behavior=deny with the classifier reason.
- ask: behavior=deny with a message explaining that the classifier requested review and Codex blocked the action, followed by the classifier reason.

Codex does not support a PermissionRequest ask behavior. Mapping ask to deny blocks the action in both manual and automatic approval modes instead of falling back to a reviewer that could approve it. This does not create a confirmation popup or change native approval settings. Claude continues to receive ask unchanged.

Missing credentials still return no override — the plugin is simply not configured, so Codex's normal flow applies. Malformed model responses and API failures on a watched call, however, now produce an explicit ask from the classifier, which this adapter maps to deny. Under Codex those cases therefore **block** the call rather than deferring it; under Claude they surface as a review prompt. Neither ever allows.

The practical consequence is that a transient network error or rate-limit response blocks a watched command under Codex. That is the intended trade — deferring would hand an unjudged call to an automatic reviewer — but it makes retrying transient failures more valuable here than on Claude, and it means a burst of 429s shows up as a burst of blocked commands rather than extra prompts.

Decision logs preserve the classifier's original decision: an ask entry means the Codex adapter returned deny. When diagnosing a block, check the returned PermissionRequest decision as well as the classifier log. Replaying a classifier input does not execute the classified command.

The hook only runs for requests that need approval, not every command. Codex sandbox/managed restrictions still apply. Decision logs use PLUGIN_DATA when supplied, otherwise `$CODEX_HOME/permissions-juditor` (default `~/.codex/permissions-juditor`). The main assistant model is independent of the classifier model. No live API call is made by unit tests.
