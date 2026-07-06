#!/usr/bin/env bash
# Bumps the version of every plugin with staged changes under plugins/<name>/,
# mirrors the new version into marketplace.json, and bumps the marketplace root
# version + updated date if any plugin was bumped. Stages the modified files
# unless --dry-run is given.
#
# Intended to be called from .git/hooks/pre-commit (with `patch`). Safe to run
# standalone with any part and/or --dry-run.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bump-plugin-versions.sh [--part major|minor|patch] [--dry-run]

  --part <major|minor|patch>   Which version segment to bump (default: patch)
  --dry-run                    Print old -> new versions per file, write nothing

Examples:
  scripts/bump-plugin-versions.sh
  scripts/bump-plugin-versions.sh --part minor
  scripts/bump-plugin-versions.sh --part major --dry-run
EOF
}

PART="patch"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --part)
      shift
      PART="${1:-}"
      case "$PART" in
        major|minor|patch) ;;
        *)
          echo "bump-plugin-versions: --part must be major, minor, or patch (got '$PART')" >&2
          usage
          exit 1
          ;;
      esac
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "bump-plugin-versions: unknown argument '$1'" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MARKETPLACE_JSON=".claude-plugin/marketplace.json"

if [[ ! -f "$MARKETPLACE_JSON" ]]; then
  echo "bump-plugin-versions: $MARKETPLACE_JSON not found, skipping" >&2
  exit 0
fi

bump_version() {
  # $1 = current semver (x.y.z), $2 = major|minor|patch -> prints bumped semver
  python3 -c "
v = [int(p) for p in '$1'.split('.')]
part = '$2'
if part == 'major':
    v = [v[0] + 1, 0, 0]
elif part == 'minor':
    v = [v[0], v[1] + 1, 0]
else:
    v = [v[0], v[1], v[2] + 1]
print('.'.join(str(p) for p in v))
"
}

mapfile -t changed_plugins < <(
  git diff --cached --name-only --diff-filter=ACMR -- 'plugins/*' \
    | sed -E 's#^plugins/([^/]+)/.*#\1#' \
    | sort -u
)

if [[ ${#changed_plugins[@]} -eq 0 ]]; then
  echo "bump-plugin-versions: no staged plugin changes, skipping" >&2
  exit 0
fi

any_bumped=0

for plugin in "${changed_plugins[@]}"; do
  plugin_json="plugins/$plugin/.claude-plugin/plugin.json"

  if [[ ! -f "$plugin_json" ]]; then
    echo "bump-plugin-versions: no plugin.json for '$plugin', skipping" >&2
    continue
  fi

  current_version="$(jq -r '.version' "$plugin_json")"
  new_version="$(bump_version "$current_version" "$PART")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $plugin_json: $current_version -> $new_version"
    echo "[dry-run] $MARKETPLACE_JSON ($plugin entry): $current_version -> $new_version"
    any_bumped=1
    continue
  fi

  jq --arg v "$new_version" '.version = $v' "$plugin_json" > "$plugin_json.tmp"
  mv "$plugin_json.tmp" "$plugin_json"

  jq --arg name "$plugin" --arg v "$new_version" \
    '(.plugins[] | select(.name == $name) | .version) = $v' \
    "$MARKETPLACE_JSON" > "$MARKETPLACE_JSON.tmp"
  mv "$MARKETPLACE_JSON.tmp" "$MARKETPLACE_JSON"

  git add "$plugin_json"
  echo "bump-plugin-versions: $plugin $current_version -> $new_version"
  any_bumped=1
done

if [[ "$any_bumped" -eq 1 ]]; then
  root_version="$(jq -r '.version' "$MARKETPLACE_JSON")"
  new_root_version="$(bump_version "$root_version" "$PART")"
  today="$(date +%Y-%m-%d)"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $MARKETPLACE_JSON (root): $root_version -> $new_root_version"
    exit 0
  fi

  jq --arg v "$new_root_version" --arg d "$today" '.version = $v | .updated = $d' \
    "$MARKETPLACE_JSON" > "$MARKETPLACE_JSON.tmp"
  mv "$MARKETPLACE_JSON.tmp" "$MARKETPLACE_JSON"

  git add "$MARKETPLACE_JSON"
  echo "bump-plugin-versions: marketplace root $root_version -> $new_root_version"
fi
