#!/bin/bash
set -euo pipefail

# UserPromptSubmit hook - logs every user prompt for later analysis
json=$(cat)

prompt=$(echo "$json" | jq -r '.prompt // empty')

# Nothing to log for an empty/whitespace-only prompt
[ -z "$(echo "$prompt" | tr -d '[:space:]')" ] && { echo '{}'; exit 0; }

log_dir="$HOME/.claude/feedback-loop"
mkdir -p "$log_dir"

# Rolling weekly log: a fresh file is started each ISO week (prompt-detector-YYYY-Www.jsonl)
week=$(date '+%Y-W%V')
log_file="$log_dir/prompt-detector-$week.jsonl"

session_id=$(echo "$json" | jq -r '.session_id // empty')
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

jq -cn \
  --arg ts "$timestamp" \
  --arg sid "$session_id" \
  --arg prompt "$prompt" \
  '{timestamp:$ts, session_id:$sid, prompt:$prompt}' \
  >> "$log_file"

# Pure side-effect logger — never inject additionalContext, never interfere with
# other UserPromptSubmit hooks (plan-guard, task-seeder) sharing this event.
echo '{}'
