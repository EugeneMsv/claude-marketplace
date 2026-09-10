#!/usr/bin/env python3
"""Log tool invocations to a monthly runtime-specific JSONL file."""
from hook_runner import append_record, context, run_hook, timestamp, tool_context


def record(event):
    if event.get("hook_event_name") != "PreToolUse":
        return
    now = timestamp()
    append_record("tool-detector-" + now.strftime("%Y-%m") + ".jsonl",
                  {**context(event, now), **tool_context(event)}, now)


if __name__ == "__main__":
    run_hook(record)
