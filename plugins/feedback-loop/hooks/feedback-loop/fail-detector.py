#!/usr/bin/env python3
"""Log Claude failure events and failed Codex results with 90-day retention."""
import re
import shlex
from pathlib import Path
from hook_runner import append_record, context, run_hook, timestamp, tool_context


def failure(event):
    if event.get("error"):
        return str(event["error"])
    response = event.get("tool_response")
    if isinstance(response, dict):
        if response.get("isError") or response.get("error"):
            return str(response.get("error") or response)
        code = response.get("exit_code")
        if isinstance(code, int) and code != 0:
            return str(response.get("output") or f"exit code {code}")
    if isinstance(response, str):
        # Native shell responses contain an explicit exit-code status line.
        match = re.search(r"(?im)^(?:Process exited with code|Exit code:)\s*(-?\d+)\s*$", response)
        if match and int(match.group(1)) != 0:
            return response
        # Codex 0.153.4 ExecCommandToolOutput sends raw output only here,
        # unlike code_mode_result, which includes exit_code. Do not infer a
        # failure from arbitrary words such as "error" in successful output.
        inputs = event.get("tool_input") or {}
        command = inputs.get("command") if isinstance(inputs, dict) else None
        if event.get("tool_name") == "Bash" and isinstance(command, str):
            try:
                argv = shlex.split(command)
            except ValueError:
                argv = []
            executable = Path(argv[0]).name if argv else ""
            if executable in {"ls", "cat", "stat", "head", "tail", "wc", "du", "rg", "grep"}:
                diagnostic = re.compile(
                    r"(?m)^" + re.escape(executable)
                    + r": .*(?:No such file or directory|Permission denied|Not a directory|Is a directory|Input/output error)(?:.*)$"
                )
                match = diagnostic.search(response)
                if match:
                    return match.group(0)
    return None



def record(event):
    if event.get("hook_event_name") not in {"PostToolUse", "PostToolUseFailure"}:
        return
    error = failure(event)
    if not error:
        return
    now = timestamp()
    append_record("fails.jsonl", {**context(event, now), **tool_context(event),
                  "error": error, "interrupted": bool(event.get("is_interrupt"))}, now)


if __name__ == "__main__":
    run_hook(record)
