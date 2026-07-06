#!/usr/bin/env bash
#
# archive-plans.sh — SOFT-DELETE plan cleanup.
#
# Archives plan files older than a given age into a dated archive subfolder
# (archive/<YYYY-MM-DD>/) inside the SAME plans directory. Never hard-deletes:
# every archived plan is recoverable by moving it back out of the archive dir.
#
# Usage: archive-plans.sh [age]
#   age = Nw (weeks) | Nd (days) | Nm (months). Default: 2w.
#
# Cleans:
#   1. Global plans:  ~/.claude/plans/*.md
#   2. Project plans: <project>/.claude/plans/*.md  (from .metadata)
#   3. Metadata:      ~/.claude/plans/.metadata  (entries for archived plans)
#   4. Hook log:      ~/.claude/logs/hook.log     (lines older than cutoff)

set -uo pipefail

# ---- color output -----------------------------------------------------------
if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BLUE=""; BOLD=""; RESET=""
fi
info()  { printf '%s%s%s\n' "$BLUE"   "$*" "$RESET"; }
ok()    { printf '%s%s%s\n' "$GREEN"  "$*" "$RESET"; }
warn()  { printf '%s%s%s\n' "$YELLOW" "$*" "$RESET"; }
err()   { printf '%s%s%s\n' "$RED"    "$*" "$RESET" >&2; }

# ---- config -----------------------------------------------------------------
GLOBAL_PLANS="${HOME}/.claude/plans"
METADATA="${GLOBAL_PLANS}/.metadata"
HOOK_LOG="${HOME}/.claude/logs/hook.log"
TODAY="$(date +%Y-%m-%d)"

usage() {
  cat <<EOF
${BOLD}archive-plans.sh${RESET} — soft-delete (archive) old plan files.

Usage: archive-plans.sh [age]
  age   Nw weeks | Nd days | Nm months   (default: 2w)

Examples:
  archive-plans.sh        # archive plans older than 2 weeks
  archive-plans.sh 3w     # older than 3 weeks
  archive-plans.sh 30d    # older than 30 days
  archive-plans.sh 1m     # older than 1 month (30 days)

Old plans are MOVED into <plans-dir>/archive/${TODAY}/ — never deleted.
EOF
}

# ---- parse age --------------------------------------------------------------
AGE="${1:-2w}"
case "$AGE" in
  -h|--help) usage; exit 0 ;;
esac

if [[ ! "$AGE" =~ ^([0-9]+)([wdm])$ ]]; then
  err "Invalid age format: '$AGE'"
  usage
  exit 1
fi
NUM="${BASH_REMATCH[1]}"
UNIT="${BASH_REMATCH[2]}"
case "$UNIT" in
  w) DAYS=$((NUM * 7)) ;;
  d) DAYS=$((NUM)) ;;
  m) DAYS=$((NUM * 30)) ;;
esac
info "Cutoff: plans not modified in the last ${DAYS} day(s) (age ${AGE})."

# ---- helpers ----------------------------------------------------------------
# Move a file into <its-dir>/archive/<TODAY>/, never overwriting.
# Echoes the archive-relative destination on success.
archive_file() {
  local src="$1"
  [ -f "$src" ] || return 1
  local dir base archive_dir dest stem ext counter
  dir="$(cd "$(dirname "$src")" && pwd)"
  base="$(basename "$src")"
  archive_dir="${dir}/archive/${TODAY}"
  mkdir -p "$archive_dir" || return 1
  dest="${archive_dir}/${base}"
  if [ -e "$dest" ]; then
    stem="${base%.*}"; ext="${base##*.}"
    counter=1
    while [ -e "${archive_dir}/${stem}-${counter}.${ext}" ]; do
      counter=$((counter + 1))
    done
    dest="${archive_dir}/${stem}-${counter}.${ext}"
  fi
  mv "$src" "$dest" || return 1
  printf 'archive/%s/%s' "$TODAY" "$(basename "$dest")"
}

# Archive every top-level *.md older than cutoff in a plans dir.
# Appends archived basenames to the global ARCHIVED_NAMES.
ARCHIVED_NAMES=""
archive_dir_plans() {
  local plans_dir="$1" label="$2" dest base
  [ -d "$plans_dir" ] || { warn "Skip ${label}: no dir ${plans_dir}"; return 0; }
  while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    if dest="$(archive_file "$f")"; then
      ok "Archived ${label}: ${base} -> ${dest}"
      ARCHIVED_NAMES+="${base}"$'\n'
    else
      err "Failed to archive ${label}: ${base}"
    fi
  done < <(find "$plans_dir" -maxdepth 1 -name '*.md' -mtime "+${DAYS}" -print0 2>/dev/null)
}

# ---- 1. global plans --------------------------------------------------------
info "${BOLD}== Global plans ==${RESET}"
PRECOUNT=$(find "$GLOBAL_PLANS" -maxdepth 1 -name '*.md' -mtime "+${DAYS}" 2>/dev/null | wc -l | tr -d ' ')
if [ "$PRECOUNT" -eq 0 ]; then
  warn "No plans older than ${AGE} found in ${GLOBAL_PLANS}."
fi
archive_dir_plans "$GLOBAL_PLANS" "global"
GLOBAL_ARCHIVED="$ARCHIVED_NAMES"

# ---- 2. project plans (from metadata) + 3. metadata update ------------------
info "${BOLD}== Project plans & metadata ==${RESET}"
if [ -f "$METADATA" ]; then
  TMP_META="$(mktemp)"
  # For each archived global plan, archive its project copy and drop the entry.
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    name="${line%%:*}"
    proj="${line#*:}"
    if printf '%s' "$GLOBAL_ARCHIVED" | grep -qxF "$name"; then
      proj_plan="${proj}/.claude/plans/${name}"
      if [ -f "$proj_plan" ]; then
        if dest="$(archive_file "$proj_plan")"; then
          ok "Archived project: ${proj_plan} -> ${dest}"
        else
          err "Failed to archive project copy: ${proj_plan}"
        fi
      fi
      info "Updated metadata: removed ${name}"
    else
      printf '%s\n' "$line" >> "$TMP_META"
    fi
  done < "$METADATA"
  mv "$TMP_META" "$METADATA"
else
  warn "No metadata file (${METADATA}); global archival only."
fi

# ---- 4. hook log trim -------------------------------------------------------
info "${BOLD}== Hook log ==${RESET}"
if [ -f "$HOOK_LOG" ]; then
  # Build cutoff date string in YYYY-MM-DD for lexical comparison against
  # ISO-8601 timestamps at the start of each log line. Lines without a parseable
  # leading date are KEPT (conservative).
  if date -v-"${DAYS}"d +%Y-%m-%d >/dev/null 2>&1; then
    CUTOFF_DATE="$(date -v-"${DAYS}"d +%Y-%m-%d)"        # BSD/macOS
  else
    CUTOFF_DATE="$(date -d "${DAYS} days ago" +%Y-%m-%d)" # GNU/Linux
  fi
  TMP_LOG="$(mktemp)"
  removed=0; kept=0
  while IFS= read -r logline; do
    if [[ "$logline" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
      if [[ "${BASH_REMATCH[1]}" < "$CUTOFF_DATE" ]]; then
        removed=$((removed + 1)); continue
      fi
    fi
    printf '%s\n' "$logline" >> "$TMP_LOG"
    kept=$((kept + 1))
  done < "$HOOK_LOG"
  mv "$TMP_LOG" "$HOOK_LOG"
  ok "Hook log cleaned: removed ${removed} lines, kept ${kept} lines (cutoff ${CUTOFF_DATE})"
else
  warn "No hook log at ${HOOK_LOG}; skipping."
fi

# ---- summary ----------------------------------------------------------------
TOTAL_ARCHIVED=$(printf '%s' "$GLOBAL_ARCHIVED" | grep -c . || true)
echo
if [ "$TOTAL_ARCHIVED" -gt 0 ]; then
  ok "✓ Archived ${TOTAL_ARCHIVED} plan(s) older than ${AGE} (recoverable in archive/${TODAY}/)"
else
  warn "No plans archived."
fi
ok "Cleanup complete!"
