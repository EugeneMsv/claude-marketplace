#!/bin/bash
set -euo pipefail

# PreToolUse hook - logs every tool invocation
json=$(cat)

log_dir="$HOME/.claude/feedback-loop"
mkdir -p "$log_dir"

# Rolling monthly log: a fresh file is started each month (tool-detector-YYYY-MM.jsonl)
month=$(date '+%Y-%m')
log_file="$log_dir/tool-detector-$month.jsonl"

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

#echo "{\"systemMessage\": \"[feedback-loop/tool-detector] $tool_name logged to $log_file\"}"
