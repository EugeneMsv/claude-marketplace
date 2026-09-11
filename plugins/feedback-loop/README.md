# feedback-loop

Local tool-use, failure, and configurable prompt logging for Claude Code and Codex. Shared skills load the selected host's procedure from `references/claude.md` or `references/codex.md`.

## Runtime

Set `AGENT_RUNTIME=claude` or `AGENT_RUNTIME=codex`. If unset, Codex's `PLUGIN_ROOT` selects Codex; otherwise Claude is the default. Invalid values cause the hook to log a diagnostic and defer. Codex data uses `PLUGIN_DATA` when available, otherwise `$CODEX_HOME/feedback-loop` (default `~/.codex/feedback-loop`). Claude uses `$CLAUDE_CONFIG_DIR/feedback-loop` (default `~/.claude/feedback-loop`). Python 3.11+ is required.

## Events and data

- PreToolUse: monthly tool inventory.
- PostToolUse: Codex shell failures (structured exit_code or native exit-status text) and MCP isError results. Unknown response formats are not guessed to be failures.
- Claude's PostToolUseFailure event: failure logging through the same logger.
- UserPromptSubmit: weekly prompt logging defaults on, preserving the existing behavior. Set `FEEDBACK_LOOP_LOG_PROMPTS=0` to disable it.

Logs stay local and are created with owner-only file permissions. Commands and prompts may contain private data; no automatic upload occurs. Failure logs retain 90 days; monthly tool logs and weekly prompt logs remain until separately archived. Hooks always defer to normal host behavior after recording evidence. Codex hooks require trust review before activation.

## Skills

- memory-refiner: grounded changes to instructions and memory.
- tool-permission-refiner: native permission proposals based on real usage.
- tool-rules-refiner: recurring failures converted into concise guidance.

Claude installation uses the existing marketplace and Claude manifest; Codex uses `.codex-plugin/plugin.json` in the same plugin root. Host-specific permission formats are never interchanged.

## Detector entry points

- `tool-detector.py`: PreToolUse → monthly tool inventory.
- `prompt-detector.py`: UserPromptSubmit → weekly prompt log.
- `fail-detector.py`: PostToolUse / PostToolUseFailure → failure log.

Each detector owns its event filtering and record content. `hook_runner.py` runs hook handlers and provides shared record context, storage, and retention helpers; `agent_runtime.py` resolves the runtime and data directory. Hook configurations invoke the Python detectors directly.

## Hook configuration

Each manifest selects one complete file: `.claude-plugin/plugin.json` → `hooks/claude.json`; `.codex-plugin/plugin.json` → `hooks/codex.json`. There is no default `hooks/hooks.json` to merge or execute twice. Both files invoke the same three Python detectors. Claude uses PostToolUseFailure for failures; Codex uses PostToolUse. Each file uses its host's plugin-root variable.

## Codex shell failure limitation

Codex 0.153.4 sends raw command output to PostToolUse without exit status (`ExecCommandToolOutput.post_tool_use_response`), although its code-mode tool result contains exit_code. The detector supports structured status when available, explicit status lines, MCP errors, and command-matched filesystem diagnostics from ls/cat/stat/head/tail/wc/du/rg/grep. It does not treat any occurrence of “error” as failure. Silent nonzero exits, including `false`, cannot be identified from an empty raw payload and are not logged as proven failures.

Source: https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/core/src/tools/context.rs
