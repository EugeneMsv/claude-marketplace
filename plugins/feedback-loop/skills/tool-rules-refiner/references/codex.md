# Codex procedure

Use `$CODEX_HOME` (default `~/.codex`). For logs, use the plugin's `PLUGIN_DATA` directory if configured by the host; otherwise `$CODEX_HOME/feedback-loop/`. If that path is not exposed to the skill, ask for or locate the installed plugin data path; do not read Claude logs by default. Logs include `runtime`, `session_id`, `tool`, and `command`; prompt logging defaults on, matching the existing Claude plugin; set `FEEDBACK_LOOP_LOG_PROMPTS=0` to disable it.

Read `fails.jsonl`, group by tool/subcommand and repeated error, and inspect AGENTS.md plus its referenced instruction files. Suggest short action-oriented additions or corrections only when supported by repeated failures (or an explicit correction). Use 🔴 STRENGTHEN, 🟡 ADD, and ⚠️ CONFLICT. Apply to an existing referenced tool-guidance file where appropriate; otherwise use a concise AGENTS.md section. Verify the reference path and avoid duplicate rules. Do not auto-delete logs.

For automatic review, preserve the sandbox and built-in policy. `[auto_review].policy` replaces policy rather than appending to it; do not overwrite it unless the complete active policy is available and the user approves the resulting full replacement. Behavioral AGENTS.md guidance is not equivalent to an enforced permission. Store temporary artifacts under `.Codex/feedback-loop/` unless project instructions override it.
