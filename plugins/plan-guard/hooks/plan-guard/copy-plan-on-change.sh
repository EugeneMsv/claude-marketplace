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
INPUT=$(cat)

log_message "debug" "[copy-plan-on-change] Hook triggered"

# Extract parameters using pure bash regex (no jq needed)
# Note: "file_path" and "cwd" keys are unique in hook input, safe to use head -1
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"\(.*\)"/\1/')
CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\(.*\)"/\1/')

# Exit if no file path provided
if [[ -z "$FILE_PATH" || -z "$CWD" ]]; then
  log_message "debug" "[copy-plan-on-change] No FILE_PATH or CWD, exiting"
  exit 0
fi

# Skip if not a plan file
if ! is_plan_file "$FILE_PATH"; then
  log_message "debug" "[copy-plan-on-change] Not a plan file: $FILE_PATH"
  exit 0
fi

log_message "info" "[copy-plan-on-change] Processing plan: FILE_PATH=$FILE_PATH, CWD=$CWD"

# Extract plan filename (needed for metadata lookup)
PLAN_FILENAME=$(extract_plan_filename "$FILE_PATH")

# Initialize metadata file path
METADATA_FILE="${HOME}/.claude/plans/.metadata"
init_metadata_file "$METADATA_FILE"

# Determine effective working directory
if is_valid_cwd "$CWD"; then
  # Valid project directory - use it
  CWD_NORMALIZED=$(get_project_root "$CWD")
  log_message "debug" "[copy-plan-on-change] Using CWD: $CWD_NORMALIZED"

  # Skip if this is ~/.claude itself (global plan)
  CLAUDE_HOME=$(normalize_path "${HOME}/.claude")
  if [[ "$CWD_NORMALIZED" == "$CLAUDE_HOME" ]]; then
    log_message "info" "[copy-plan-on-change] Global plan (in ~/.claude), skipping metadata/sync"
    exit 0
  fi
else
  # Invalid CWD - try to use metadata for existing plans
  log_message "debug" "[copy-plan-on-change] Invalid CWD ($CWD), checking metadata"

  ASSOCIATED_PROJECT=$(get_plan_association "$METADATA_FILE" "$PLAN_FILENAME" || echo "")

  if [[ -z "$ASSOCIATED_PROJECT" ]]; then
    log_message "warn" "[copy-plan-on-change] New plan with invalid CWD. Start Claude from project directory."
    exit 0
  fi

  # Use metadata path for existing plans
  CWD_NORMALIZED="$ASSOCIATED_PROJECT"
  log_message "debug" "[copy-plan-on-change] Using metadata: $CWD_NORMALIZED"
fi

log_message "debug" "[copy-plan-on-change] Plan: $PLAN_FILENAME, Normalized CWD: $CWD_NORMALIZED"

# Get or create plan association
log_message "debug" "[copy-plan-on-change] Getting association for $PLAN_FILENAME from $METADATA_FILE"
ASSOCIATED_PROJECT=$(get_plan_association "$METADATA_FILE" "$PLAN_FILENAME" || echo "")
log_message "debug" "[copy-plan-on-change] Associated project: ${ASSOCIATED_PROJECT:-<none>}"

if [[ -z "$ASSOCIATED_PROJECT" ]]; then
  # First time seeing this plan - register it
  set_plan_association "$METADATA_FILE" "$PLAN_FILENAME" "$CWD_NORMALIZED"
  ASSOCIATED_PROJECT="$CWD_NORMALIZED"
  log_message "info" "Plan registered: $PLAN_FILENAME -> $CWD_NORMALIZED"
fi

# Sync if current directory matches registered project
if [[ "$CWD_NORMALIZED" == "$ASSOCIATED_PROJECT" ]]; then
  TARGET_DIR="$CWD_NORMALIZED/.claude/plans"
  sync_plan_file "$FILE_PATH" "$TARGET_DIR" "$PLAN_FILENAME"
else
  log_message "info" "Plan skipped: $PLAN_FILENAME belongs to $ASSOCIATED_PROJECT, not $CWD_NORMALIZED"
fi

exit 0
