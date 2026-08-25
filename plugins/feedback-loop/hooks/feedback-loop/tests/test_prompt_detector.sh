#!/usr/bin/env bash
# Verifies prompt-detector.sh: logs prompt/timestamp/session_id to a
# weekly-rotated jsonl file, skips empty prompts, always emits bare {} so it
# never interferes with other UserPromptSubmit hooks (plan-guard, task-seeder)
# sharing this event. Uses an isolated temp HOME and a stubbed `date` binary
# to deterministically control which ISO week each run lands in.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SCRIPT="$SCRIPT_DIR/../prompt-detector.sh"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FAKE_HOME="$WORKDIR/home"
FAKE_BIN="$WORKDIR/bin"
mkdir -p "$FAKE_HOME" "$FAKE_BIN"

# Stub `date` so week 1's run reports 2026-W01 and week 2's run reports
# 2026-W02, regardless of when the test actually executes.
make_date_stub() {
  local week_label="$1"
  cat > "$FAKE_BIN/date" <<EOF
#!/bin/bash
if [[ "\$1" == "+%Y-W%V" ]]; then
  echo "$week_label"
else
  exec /bin/date "\$@"
fi
EOF
  chmod +x "$FAKE_BIN/date"
}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

log_dir="$FAKE_HOME/.claude/feedback-loop"

# --- week 1: a normal prompt gets logged with the three expected fields ---
make_date_stub "2026-W01"
echo '{"session_id":"sess-aaa","prompt":"Refactor the auth middleware to use JWT."}' \
  | env HOME="$FAKE_HOME" PATH="$FAKE_BIN:$PATH" bash "$HOOK_SCRIPT" > /tmp/prompt_detector_test_stdout.$$

grep -q '^{}$' /tmp/prompt_detector_test_stdout.$$ \
  || fail "hook must emit bare {} — got: $(cat /tmp/prompt_detector_test_stdout.$$)"
rm -f /tmp/prompt_detector_test_stdout.$$

week1_file="$log_dir/prompt-detector-2026-W01.jsonl"
[[ -f "$week1_file" ]] || fail "expected week-1 log file not created: $week1_file"

record=$(cat "$week1_file")
echo "$record" | jq -e '.session_id == "sess-aaa"' > /dev/null \
  || fail "session_id not recorded correctly"
echo "$record" | jq -e '.prompt == "Refactor the auth middleware to use JWT."' > /dev/null \
  || fail "prompt not recorded correctly"
echo "$record" | jq -e '.timestamp | length > 0' > /dev/null \
  || fail "timestamp missing or empty"

# --- empty/whitespace-only prompt: skipped, no new line appended ---
echo '{"session_id":"sess-aaa","prompt":"   "}' \
  | env HOME="$FAKE_HOME" PATH="$FAKE_BIN:$PATH" bash "$HOOK_SCRIPT" > /dev/null

line_count=$(wc -l < "$week1_file" | tr -d ' ')
[[ "$line_count" == "1" ]] || fail "empty prompt must not be logged (line count: $line_count)"

# --- week 2: a new prompt lands in a separate weekly file, not the week-1 file ---
make_date_stub "2026-W02"
echo '{"session_id":"sess-bbb","prompt":"Add input validation to the signup form."}' \
  | env HOME="$FAKE_HOME" PATH="$FAKE_BIN:$PATH" bash "$HOOK_SCRIPT" > /dev/null

week2_file="$log_dir/prompt-detector-2026-W02.jsonl"
[[ -f "$week2_file" ]] || fail "expected week-2 log file not created: $week2_file"

week1_line_count=$(wc -l < "$week1_file" | tr -d ' ')
[[ "$week1_line_count" == "1" ]] \
  || fail "week-2 entry leaked into week-1 file (line count: $week1_line_count)"

echo "test_prompt_detector: all checks passed"
