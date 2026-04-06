#!/bin/bash

# Initialize metadata file if it doesn't exist
init_metadata_file() {
  local metadata_file="${1}"
  if [[ ! -f "$metadata_file" ]]; then
    touch "$metadata_file"
  fi
}

# Migrate from old JSON format to line-based format
migrate_metadata_if_needed() {
  local old_json="${HOME}/.claude/plan-projects.json"
  local new_txt="${HOME}/.claude/plans/.metadata"

  # Skip if already migrated
  [[ -f "$new_txt" ]] && return 0

  # Skip if old file doesn't exist
  [[ ! -f "$old_json" ]] && return 0

  log_message "info" "Migrating metadata from JSON to line-based format"

  # Backup old file
  cp "$old_json" "${old_json}.backup"

  # Convert JSON to line-based format using Python (available on macOS)
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "
import json
import sys

try:
    with open('${old_json}', 'r') as f:
        data = json.load(f)

    with open('${new_txt}', 'w') as f:
        for plan, project in data.items():
            f.write(f'{plan}:{project}\n')

    print('[Migration] Converted ${old_json} to ${new_txt}', file=sys.stderr)
except Exception as e:
    print(f'[Migration Error] {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1
  else
    # Fallback: provide manual migration notice
    log_message "warn" "Python3 not available. Please manually convert plan-projects.json to plan-projects.txt format: plan-name.md:/path/to/project"
  fi
}

# Get project association for a plan (line-based format)
get_plan_association() {
  local metadata_file="${1}"
  local plan_filename="${2}"

  if [[ ! -f "$metadata_file" ]]; then
    echo ""
    return 0
  fi

  # Find line starting with plan filename, extract path after first colon
  grep "^${plan_filename}:" "$metadata_file" 2>/dev/null | cut -d: -f2- | head -1
}

# Set project association for a plan (line-based format)
set_plan_association() {
  local metadata_file="${1}"
  local plan_filename="${2}"
  local project_path="${3}"

  # Create file if doesn't exist
  touch "$metadata_file"

  # Remove old entry if exists, then append new entry (atomic operation)
  local temp_file="${metadata_file}.tmp.$$"
  grep -v "^${plan_filename}:" "$metadata_file" 2>/dev/null > "$temp_file" || true
  echo "${plan_filename}:${project_path}" >> "$temp_file"
  mv "$temp_file" "$metadata_file"
}

# Normalize path to absolute form
normalize_path() {
  local path="${1}"
  if [[ -d "$path" ]]; then
    (cd "$path" && pwd)
  else
    echo "$path"
  fi
}

# Extract plan filename from full path
extract_plan_filename() {
  local file_path="${1}"
  basename "$file_path"
}

# Get most recent plan file
get_latest_plan_file() {
  local plans_dir="${HOME}/.claude/plans"
  local latest
  latest=$(ls -t "$plans_dir"/*.md 2>/dev/null | head -1)
  echo "${latest}"
}

# Copy plan file to destination
sync_plan_file() {
  local source_file="${1}"
  local dest_dir="${2}"
  local plan_filename="${3}"

  if [[ ! -f "$source_file" ]]; then
    log_message "error" "Source plan file not found: $source_file"
    return 1
  fi

  mkdir -p "$dest_dir"
  cp "$source_file" "$dest_dir/$plan_filename"
  log_message "info" "Plan synced: $plan_filename -> $dest_dir/"
  return 0
}

# Log message with timestamp
log_message() {
  local level="${1}"
  shift
  local message="$*"

  # Get configured log level (default: info)
  local configured_level="${CLAUDE_HOOK_LOG_LEVEL:-info}"

  # Convert level to priority (0=debug, 1=info, 2=warn, 3=error)
  local msg_priority=0
  case "$level" in
    debug) msg_priority=0 ;;
    info)  msg_priority=1 ;;
    warn)  msg_priority=2 ;;
    error) msg_priority=3 ;;
    *)     msg_priority=0 ;;
  esac

  local config_priority=1
  case "$configured_level" in
    debug) config_priority=0 ;;
    info)  config_priority=1 ;;
    warn)  config_priority=2 ;;
    error) config_priority=3 ;;
    *)     config_priority=1 ;;
  esac

  # Only log if message level >= configured level
  if (( msg_priority >= config_priority )); then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $message" >&2
  fi
}

# Check if file is a plan file
is_plan_file() {
  local file_path="${1}"
  [[ "$file_path" == *"/.claude/plans/"* ]] && [[ "$file_path" == *.md ]]
}

# Check if CWD is valid (not ~/.claude)
is_valid_cwd() {
  local cwd="${1}"
  local claude_home
  claude_home=$(normalize_path "${HOME}/.claude")
  local cwd_normalized
  cwd_normalized=$(normalize_path "$cwd")

  [[ "$cwd_normalized" != "$claude_home" ]]
}

# Get project root (git root if in repo, otherwise normalized CWD)
get_project_root() {
  local cwd="${1}"
  local git_root

  # Try to get git root
  git_root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || echo "")

  if [[ -n "$git_root" ]]; then
    echo "$git_root"
  else
    # Fall back to normalized CWD for non-git projects
    normalize_path "$cwd"
  fi
}
