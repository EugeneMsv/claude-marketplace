#!/bin/bash
set -euo pipefail

# PostToolUseFailure hook - receives failures with 'error' field
json=$(cat)
error_msg=$(echo "$json" | jq -r '.error // empty')

# Skip if no error (shouldn't happen in PostToolUseFailure, but defensive)
[ -z "$error_msg" ] && exit 0

log_dir="$HOME/.claude/feedback-loop"
mkdir -p "$log_dir"
log_file="$log_dir/fails.jsonl"

tool_name=$(echo "$json" | jq -r '.tool_name')
command=$(echo "$json" | jq -r '.tool_input.command // .tool_input // empty')
is_interrupt=$(echo "$json" | jq -r '.is_interrupt // false')
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

jq -cn \
  --arg ts "$timestamp" \
  --arg tool "$tool_name" \
  --arg cmd "$command" \
  --arg err "$error_msg" \
  --argjson interrupted "$is_interrupt" \
  '{timestamp:$ts, tool:$tool, command:$cmd, error:$err, interrupted:$interrupted}' \
  >> "$log_file"

# Purge entries older than 3 months
cutoff=$(date -v-3m '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '3 months ago' '+%Y-%m-%d %H:%M:%S')
tmp=$(mktemp)
jq -c --arg cutoff "$cutoff" 'select(.timestamp >= $cutoff)' "$log_file" > "$tmp" && mv "$tmp" "$log_file"

echo "{\"systemMessage\": \"[feedback-loop/fail-detector] Failure recorded to $log_file\"}"
