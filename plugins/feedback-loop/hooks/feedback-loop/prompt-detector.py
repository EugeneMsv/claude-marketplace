#!/usr/bin/env python3
"""Log nonempty user prompts by ISO week, unless explicitly disabled."""
import os
from hook_runner import append_record, context, run_hook, timestamp


def record(event):
    if event.get("hook_event_name") != "UserPromptSubmit":
        return
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return
    if os.environ.get("FEEDBACK_LOOP_LOG_PROMPTS", "1") != "1":
        return
    now = timestamp()
    append_record("prompt-detector-" + now.strftime("%G-W%V") + ".jsonl",
                  {**context(event, now), "prompt": prompt}, now)


if __name__ == "__main__":
    run_hook(record)
