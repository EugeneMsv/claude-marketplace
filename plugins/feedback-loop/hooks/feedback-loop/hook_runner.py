"""Shared local JSONL storage and hook input/output helpers."""
import datetime as dt
import fcntl
import json
import os
import sys
from agent_runtime import data_dir, runtime_name


def timestamp():
    return dt.datetime.now(dt.timezone.utc)


def context(event, now):
    return {"timestamp": now.isoformat(), "session_id": event.get("session_id", ""),
            "runtime": runtime_name(), "tool_use_id": event.get("tool_use_id", "")}


def tool_context(event):
    inputs = event.get("tool_input") or {}
    if not isinstance(inputs, dict):
        inputs = {}
    command = inputs.get("command") or inputs.get("file_path") or inputs.get("pattern") or ",".join(sorted(inputs))
    return {"tool": event.get("tool_name", ""), "command": str(command)}


def append_record(filename, record, now):
    directory = data_dir("feedback-loop")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (json.dumps(record, ensure_ascii=False) + "\n").encode()
    with (directory / ".logger.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd = os.open(directory / filename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        if filename == "fails.jsonl":
            path = directory / filename
            cutoff = now - dt.timedelta(days=90)
            retained = []
            for line in path.read_text().splitlines(keepends=True):
                try:
                    timestamp = dt.datetime.fromisoformat(json.loads(line)["timestamp"])
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
                    if timestamp >= cutoff:
                        retained.append(line)
                except (ValueError, TypeError, KeyError):
                    retained.append(line)  # do not silently erase unknown old records
            # All writers use the separate lock, so replacement does not lose records.
            temporary = directory / ".fails-retention.tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.writelines(retained)
            os.replace(temporary, path)



def run_hook(handler):
    try:
        event = json.load(sys.stdin)
        if isinstance(event, dict):
            handler(event)
    except (ValueError, TypeError, OSError) as error:
        print(f"feedback-loop: {type(error).__name__}", file=sys.stderr)
    print("{}")
