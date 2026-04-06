#!/bin/bash
set -euo pipefail

# PreToolUse hook - logs every tool invocation
json=$(cat)

log_dir="$HOME/.claude/feedback-loop"
mkdir -p "$log_dir"
log_file="$log_dir/tool-detector.jsonl"

tool_name=$(echo "$json" | jq -r '.tool_name')
command=$(echo "$json" | jq -r '
  .tool_name as $t |
  if $t == "Bash" then .tool_input.command
  elif ($t == "Edit" or $t == "Write") then .tool_input.file_path
  elif $t == "Read" then .tool_input.file_path
  elif $t == "Glob" then .tool_input.pattern
  elif $t == "Grep" then .tool_input.pattern
  else (.tool_input | keys | join(","))
  end // empty')
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

jq -cn \
  --arg ts "$timestamp" \
  --arg tool "$tool_name" \
  --arg cmd "$command" \
  '{timestamp:$ts, tool:$tool, command:$cmd}' \
  >> "$log_file"

# Purge entries older than 3 months
cutoff=$(date -v-3m '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '3 months ago' '+%Y-%m-%d %H:%M:%S')
tmp=$(mktemp)
jq -c --arg cutoff "$cutoff" 'select(.timestamp >= $cutoff)' "$log_file" > "$tmp" && mv "$tmp" "$log_file"

echo "{\"systemMessage\": \"[feedback-loop/tool-detector] $tool_name logged to $log_file\"}"
