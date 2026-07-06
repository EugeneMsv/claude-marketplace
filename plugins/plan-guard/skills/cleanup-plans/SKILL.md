---
name: msv-cleanup-plans
version: 2.0.0
description: |
  This skill should be used when the user asks to "cleanup old plans",
  "delete old plans", "remove plans older than", "cleanup plans",
  "/cleanup-plans", or discusses plan file cleanup and maintenance.
  Supports parameterized age (2w, 30d, 1m) with default of 2 weeks.
  Cleanup is ALWAYS a soft delete: old plans are archived, never hard-deleted.
---

# Cleanup Plans Skill

Manual plan cleanup with parameterized age support. **Soft delete only** — old
plans are archived in place, never removed with `rm`.

## When This Skill Activates

- User invokes `/cleanup-plans [age]`
- User asks to "cleanup old plans"
- User mentions deleting or removing old plan files

## Soft Delete Contract (MUST FOLLOW)

- **NEVER hard-delete** a plan file. No `rm`, no unlink, no overwrite.
- Cleanup = **archive**: move each old plan into an `archive/<YYYY-MM-DD>/`
  subfolder **inside the same plans directory**, where `<YYYY-MM-DD>` is the
  date of archivation (today). The plan stays in the same folder tree and is
  always recoverable by moving it back.
- The archive subfolder lives beside the plans (`<plans-dir>/archive/...`), so
  the originals are never lost and a misfire is always reversible.
- Future cleanup runs scan **only top-level `*.md`** (maxdepth 1), so already
  archived plans are skipped and never re-processed.

## What Gets Cleaned

When this skill is activated, it archives:

1. **Global plan files**: `~/.claude/plans/*.md` → `~/.claude/plans/archive/<YYYY-MM-DD>/`
2. **Project plan files**: `/project/.claude/plans/*.md` (from metadata) → `/project/.claude/plans/archive/<YYYY-MM-DD>/`
3. **Metadata entries**: `~/.claude/plans/.metadata` (entries for archived plans removed)
4. **Hook log entries**: `~/.claude/logs/hook.log` (lines older than cutoff)

## Workflow

When this skill is activated, follow these steps:

1. **Parse age parameter** - Accept optional age in formats: `Nw` (weeks), `Nd` (days), `Nm` (months). Default: `2w`
2. **Calculate cutoff date** - Determine the timestamp for files older than the specified age
3. **Find plans older than cutoff** - Search top-level `*.md` only (maxdepth 1), based on last modification time (mtime)
4. **Archive from global location** - Move old plans from `~/.claude/plans/` into `~/.claude/plans/archive/<YYYY-MM-DD>/` (create the dir if missing)
5. **Archive from project locations** - Use metadata to find project-specific copies and move them into `<project>/.claude/plans/archive/<YYYY-MM-DD>/`
6. **Update metadata** - Remove entries for archived plans from `~/.claude/plans/.metadata`
7. **Clean hook log** - Remove log entries older than cutoff from `~/.claude/logs/hook.log`
8. **Show summary** - Report number of plans archived, archive paths, and log cleanup results

## Age Parameter Format

Supported formats:
- `Nw`: N weeks (e.g., `2w` = 14 days)
- `Nd`: N days (e.g., `30d` = 30 days)
- `Nm`: N months (e.g., `1m` = 30 days)

**Default**: `2w` (14 days if no parameter provided)

## Implementation

Execute the cleanup script with the provided or default age parameter:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/cleanup-plans/scripts/archive-plans.sh [age]
```

The script will:
- Parse and validate the age parameter
- Calculate the cutoff timestamp
- Find all top-level plan files older than the cutoff (maxdepth 1)
- **Archive** plans (move, never delete) from both global and project-specific
  locations into an `archive/<YYYY-MM-DD>/` subfolder of the same plans dir
- Update the metadata file
- Display a summary of archived plans and their archive destination

If the script is absent, perform the archival manually following the Soft
Delete Contract above — use `mv` into the dated archive folder, never `rm`.

## Usage Examples

```bash
# Archive plans older than 2 weeks (default)
/cleanup-plans

# Archive plans older than 3 weeks
/cleanup-plans 3w

# Archive plans older than 30 days
/cleanup-plans 30d

# Archive plans older than 1 month
/cleanup-plans 1m
```

## Safety Notes

- **Soft delete only** — plans are moved into a dated archive folder, never `rm`'d
- Archive lives in the **same plans directory** under `archive/<YYYY-MM-DD>/`
- Recovery = move the file back out of `archive/<date>/` to its plans dir
- Uses **last modification time (mtime)**, not creation time
- Plans that are edited get "renewed" and their lifetime extended
- Scans **top-level only** (maxdepth 1) so archived plans are never re-archived
- Archives from **both global and project-specific** locations
- **Handles missing metadata gracefully**: If `plans/.metadata` doesn't exist, only archives global `~/.claude/plans/` without errors
- **Updates metadata automatically**: If `plans/.metadata` exists, removes entries for all archived plans
- Each archive operation is independent (failure on one doesn't stop others)
- A name collision in the archive dir must NOT overwrite — suffix with a counter instead
- 2-week default prevents accidental archival of recent plans
- Shows summary before exit

## Expected Output

```
Found 3 plans older than 2w:
old-plan-1.md
old-plan-2.md
old-plan-3.md

Archived global: old-plan-1.md -> archive/2026-06-28/old-plan-1.md
Archived project: /path/to/project/.claude/plans/old-plan-1.md -> archive/2026-06-28/old-plan-1.md
Updated metadata: removed old-plan-1.md
Archived global: old-plan-2.md -> archive/2026-06-28/old-plan-2.md
Updated metadata: removed old-plan-2.md
Archived global: old-plan-3.md -> archive/2026-06-28/old-plan-3.md
Archived project: /path/to/project/.claude/plans/old-plan-3.md -> archive/2026-06-28/old-plan-3.md
Updated metadata: removed old-plan-3.md

✓ Archived 3 plans older than 2w (recoverable in archive/2026-06-28/)

Cleaning hook log entries older than cutoff...
Hook log cleaned: removed 1523 lines, kept 312 lines

Cleanup complete!
```

## Error Handling

- **Invalid age format**: Shows error and usage instructions
- **No old plans found**: Reports "No plans older than X found."
- **Missing metadata file**: Continues with global archival only
- **Missing project plans**: Continues without error
- **Archive name collision**: Suffix with `-1`, `-2`, … — never overwrite
- **Permission errors**: Reports and continues with remaining plans
