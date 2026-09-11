# Codex procedure

Use `$CODEX_HOME` (default `~/.codex`). For logs, use the plugin's `PLUGIN_DATA` directory if configured by the host; otherwise `$CODEX_HOME/feedback-loop/`. If that path is not exposed to the skill, ask for or locate the installed plugin data path; do not read Claude logs by default. Logs include `runtime`, `session_id`, `tool`, and `command`; prompt logging defaults on, matching the existing Claude plugin; set `FEEDBACK_LOOP_LOG_PROMPTS=0` to disable it.

Read current and previous monthly `tool-detector-YYYY-MM.jsonl` logs. Inventory commands and MCP calls with counts and concrete examples. Inspect active user/project config.toml, `.rules` files under their rules directories, and managed restrictions when readable. Never infer effective permission solely from one file.

For shell rules, use `prefix_rule(pattern=[...], decision="allow"|"prompt"|"forbidden")` and validate proposals with `codex execpolicy check --rules <file> -- <argv>`. Prefix matching is not arbitrary shell glob matching; account for argument ordering, wrappers, and more restrictive matches. Do not turn arbitrary Python, shell interpreters, or broad CLI prefixes into allow rules.

For configured MCP servers, use per-tool `approval_mode` in config.toml (`approve` for preapproval, `prompt` for review), or `disabled_tools` to disable a tool. Verify current supported schema before changing it. Do not invent absent server connections. Report ADD, PROMPT, FORBID, COVERED, and UNSUPPORTED with exact config layer, before/after, and evidence. A prompt can route to automatic review; it is not necessarily a human prompt.

For automatic review, preserve the sandbox and built-in policy. `[auto_review].policy` replaces policy rather than appending to it; do not overwrite it unless the complete active policy is available and the user approves the resulting full replacement. Behavioral AGENTS.md guidance is not equivalent to an enforced permission. Store temporary artifacts under `.Codex/feedback-loop/` unless project instructions override it.
