#!/usr/bin/env python3
"""Log Claude failure events and failed Codex results with 90-day retention."""
import re
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
