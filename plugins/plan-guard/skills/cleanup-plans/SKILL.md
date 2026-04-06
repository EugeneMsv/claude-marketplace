---
name: cleanup-plans
version: 1.0.0
description: |
  This skill should be used when the user asks to "cleanup old plans",
  "delete old plans", "remove plans older than", "cleanup plans",
  "/cleanup-plans", or discusses plan file cleanup and maintenance.
  Supports parameterized age (2w, 30d, 1m) with default of 2 weeks.
---

# Cleanup Plans Skill

Manual plan cleanup with parameterized age support.

## When This Skill Activates

- User invokes `/cleanup-plans [age]`
- User asks to "cleanup old plans"
- User mentions deleting or removing old plan files

## What Gets Cleaned

When this skill is activated, it cleans:

1. **Global plan files**: `~/.claude/plans/*.md`
2. **Project plan files**: `/project/.claude/plans/*.md` (from metadata)
3. **Metadata entries**: `~/.claude/plans/.metadata`
4. **Hook log entries**: `~/.claude/logs/hook.log` (lines older than cutoff)

## Workflow

When this skill is activated, follow these steps:

1. **Parse age parameter** - Accept optional age in formats: `Nw` (weeks), `Nd` (days), `Nm` (months). Default: `2w`
2. **Calculate cutoff date** - Determine the timestamp for files older than the specified age
3. **Find plans older than cutoff** - Search based on last modification time (mtime)
4. **Delete from global location** - Remove plan files from `~/.claude/plans/`
5. **Delete from project locations** - Use metadata to find and delete project-specific copies
6. **Update metadata** - Remove entries for deleted plans from `~/.claude/plans/.metadata`
7. **Clean hook log** - Remove log entries older than cutoff from `~/.claude/logs/hook.log`
8. **Show summary** - Report number of plans deleted and log cleanup results

## Age Parameter Format

Supported formats:
- `Nw`: N weeks (e.g., `2w` = 14 days)
- `Nd`: N days (e.g., `30d` = 30 days)
- `Nm`: N months (e.g., `1m` = 30 days)

**Default**: `2w` (14 days if no parameter provided)

## Implementation

Execute the cleanup script with the provided or default age parameter:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/cleanup-plans/scripts/cleanup-plans.sh [age]
```

The script will:
- Parse and validate the age parameter
- Calculate the cutoff timestamp
- Find all plan files older than the cutoff
- Delete plans from both global and project-specific locations
- Update the metadata file
- Display a summary of deleted plans

## Usage Examples

```bash
# Cleanup plans older than 2 weeks (default)
/cleanup-plans

# Cleanup plans older than 3 weeks
/cleanup-plans 3w

# Cleanup plans older than 30 days
/cleanup-plans 30d

# Cleanup plans older than 1 month
/cleanup-plans 1m
```

## Safety Notes

- Uses **last modification time (mtime)**, not creation time
- Plans that are edited get "renewed" and their lifetime extended
- Deletes from **both global and project-specific** locations
- **Handles missing metadata gracefully**: If `plans/.metadata` doesn't exist, only cleans up global `~/.claude/plans/` directory without errors
- **Updates metadata automatically**: If `plans/.metadata` exists, removes entries for all deleted plans
- Each deletion is independent (failure on one doesn't stop others)
- 2-week default prevents accidental deletion of recent plans
- Shows summary before exit

## Expected Output

```
Found 3 plans older than 2w:
old-plan-1.md
old-plan-2.md
old-plan-3.md

Deleted global: old-plan-1.md
Deleted project: /path/to/project/.claude/plans/old-plan-1.md
Updated metadata: removed old-plan-1.md
Deleted global: old-plan-2.md
Updated metadata: removed old-plan-2.md
Deleted global: old-plan-3.md
Deleted project: /path/to/project/.claude/plans/old-plan-3.md
Updated metadata: removed old-plan-3.md

✓ Deleted 3 plans older than 2w

Cleaning hook log entries older than cutoff...
Hook log cleaned: removed 1523 lines, kept 312 lines

Cleanup complete!
```

## Error Handling

- **Invalid age format**: Shows error and usage instructions
- **No old plans found**: Reports "No plans older than X found."
- **Missing metadata file**: Continues with global cleanup only
- **Missing project plans**: Continues without error
- **Permission errors**: Reports and continues with remaining plans
