#!/bin/bash
set -euo pipefail

# Enable logging
mkdir -p ~/.claude/logs
exec 1>> ~/.claude/logs/hook.log 2>&1

# Source shared library
PLAN_SYNC_LIB="${CLAUDE_PLUGIN_ROOT}/hooks/plan-guard/plan-sync-utils.sh"
if [[ ! -f "$PLAN_SYNC_LIB" ]]; then
  echo "error: plan-sync-utils.sh library not found at $PLAN_SYNC_LIB" >&2
  exit 1
fi
source "$PLAN_SYNC_LIB"

# Read hook input
json=$(cat)

log_message "debug" "[copy-plan-on-exit] Hook triggered"

# Extract parameters using pure bash regex (no jq needed)
tool_name=$(echo "$json" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\(.*\)"/\1/')
cwd=$(echo "$json" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\(.*\)"/\1/')

log_message "debug" "[copy-plan-on-exit] tool_name=$tool_name, cwd=$cwd"

# Only process ExitPlanMode events
[[ "$tool_name" != "ExitPlanMode" ]] && exit 0

# Get latest plan file (needed for metadata lookup)
plan_file=$(get_latest_plan_file)
if [[ -z "$plan_file" ]]; then
  log_message "warn" "[copy-plan-on-exit] No plan file found"
  exit 0
fi

plan_name=$(extract_plan_filename "$plan_file")

# Initialize metadata
METADATA_FILE="${HOME}/.claude/plans/.metadata"
init_metadata_file "$METADATA_FILE"

# Determine effective CWD
if is_valid_cwd "$cwd"; then
  cwd_normalized=$(get_project_root "$cwd")
  log_message "debug" "[copy-plan-on-exit] Using valid CWD: $cwd"

  # Skip if this is ~/.claude itself (global plan)
  claude_home=$(normalize_path "${HOME}/.claude")
  if [[ "$cwd_normalized" == "$claude_home" ]]; then
    log_message "info" "[copy-plan-on-exit] Global plan (in ~/.claude), skipping metadata/sync"
    exit 0
  fi

  EFFECTIVE_CWD="$cwd_normalized"
else
  # Invalid CWD - try to use metadata
  log_message "warn" "[copy-plan-on-exit] Invalid CWD ($cwd), checking metadata"

  associated_project=$(get_plan_association "$METADATA_FILE" "$plan_name" || echo "")

  if [[ -z "$associated_project" ]]; then
    log_message "warn" "[copy-plan-on-exit] No metadata for plan, cannot sync"
    exit 0
  fi

  EFFECTIVE_CWD="$associated_project"
  cwd_normalized="$associated_project"
  log_message "debug" "[copy-plan-on-exit] Using metadata: $EFFECTIVE_CWD"
fi

log_message "info" "[copy-plan-on-exit] Processing plan: $plan_name"

# Register or update plan association
log_message "debug" "[copy-plan-on-exit] cwd_normalized=$cwd_normalized"

associated_project=$(get_plan_association "$METADATA_FILE" "$plan_name" || echo "")

if [[ -z "$associated_project" ]]; then
  # New plan - register it
  set_plan_association "$METADATA_FILE" "$plan_name" "$cwd_normalized"
  associated_project="$cwd_normalized"
  log_message "info" "[copy-plan-on-exit] Plan registered: $plan_name -> $cwd_normalized"
else
  log_message "debug" "[copy-plan-on-exit] Plan already associated: $plan_name -> $associated_project"
fi

# Sync plan file only if CWD matches plan's registered project
if [[ "$cwd_normalized" == "$associated_project" ]]; then
  target_dir="$EFFECTIVE_CWD/.claude/plans"
  sync_plan_file "$plan_file" "$target_dir" "$plan_name"
else
  log_message "info" "[copy-plan-on-exit] Plan skipped: $plan_name belongs to $associated_project, not $cwd_normalized"
fi
