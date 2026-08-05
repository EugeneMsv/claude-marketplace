#!/usr/bin/env bash
# Verifies sync-shared-files.sh: --dry-run reports drift without writing, and a
# real run makes each target byte-identical to its common/ source. Builds an
# isolated throwaway git repo so it never touches the real marketplace tree.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/../sync-shared-files.sh"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

cd "$WORKDIR"
git init -q .

mkdir -p common
mkdir -p plugins/plugin-a/hooks/plugin-a
mkdir -p plugins/plugin-b/hooks/plugin-b

echo "canonical v1" > common/shared_lib.py
echo "stale v0" > plugins/plugin-a/hooks/plugin-a/shared_lib.py
echo "canonical v1" > plugins/plugin-b/hooks/plugin-b/shared_lib.py  # already in sync

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# --- dry-run reports drift, writes nothing ---
dry_run_output="$(bash "$SYNC_SCRIPT" --dry-run)"

echo "$dry_run_output" | grep -q "plugin-a/hooks/plugin-a/shared_lib.py" \
  || fail "dry-run did not report the stale plugin-a target"

echo "$dry_run_output" | grep -q "plugin-b/hooks/plugin-b/shared_lib.py" \
  && fail "dry-run reported plugin-b, which was already in sync"

grep -q "stale v0" plugins/plugin-a/hooks/plugin-a/shared_lib.py \
  || fail "dry-run wrote to a target file — it must not"

# --- real run syncs the stale target, leaves the in-sync one untouched ---
bash "$SYNC_SCRIPT" > /dev/null

cmp -s common/shared_lib.py plugins/plugin-a/hooks/plugin-a/shared_lib.py \
  || fail "plugin-a target was not synced to match common/"

cmp -s common/shared_lib.py plugins/plugin-b/hooks/plugin-b/shared_lib.py \
  || fail "plugin-b target no longer matches common/ after sync"

echo "test_sync_shared_files: all checks passed"
