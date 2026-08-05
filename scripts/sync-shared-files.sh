#!/usr/bin/env bash
# Copies canonical shared files from common/ into every plugin that already
# vendors its own copy under plugins/<name>/hooks/<name>/<file>. Plugin
# installs only bundle each plugin's own plugins/<name>/** subtree, so a
# common/ file is never reachable at runtime — this script is how a single
# source of truth gets duplicated into each consuming plugin.
#
# Safe to run standalone with or without --dry-run.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sync-shared-files.sh [--dry-run]

  --dry-run   Print which plugin targets would be updated, write nothing

Examples:
  scripts/sync-shared-files.sh
  scripts/sync-shared-files.sh --dry-run
EOF
}

DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "sync-shared-files: unknown argument '$1'" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

COMMON_DIR="common"

if [[ ! -d "$COMMON_DIR" ]]; then
  echo "sync-shared-files: $COMMON_DIR not found, skipping" >&2
  exit 0
fi

any_synced=0

for source_file in "$COMMON_DIR"/*.py; do
  [[ -f "$source_file" ]] || continue
  filename="$(basename "$source_file")"

  for target_file in plugins/*/hooks/*/"$filename"; do
    [[ -f "$target_file" ]] || continue

    if cmp -s "$source_file" "$target_file"; then
      continue
    fi

    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] $target_file: would sync from $source_file"
      any_synced=1
      continue
    fi

    cp "$source_file" "$target_file"
    git add "$target_file"
    echo "sync-shared-files: $target_file <- $source_file"
    any_synced=1
  done
done

if [[ "$any_synced" -eq 0 ]]; then
  echo "sync-shared-files: everything already in sync, nothing to do" >&2
fi
