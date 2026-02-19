# AI Contribution Tracker

Automatically tracks AI vs human contributions in your codebase and injects statistics into git commit messages.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [How It Works](#how-it-works)
- [Format Attribution Details](#format-attribution-details)
- [Installation](#installation)
- [Configuration](#configuration)
- [MR Title Stats, Auto-Creation & Labeling](#mr-title-stats-auto-creation--labeling)
- [Example](#example)
- [Tracking Files](#tracking-files)
- [Disabling](#disabling)
- [Structure](#structure)
- [Testing](#testing)
- [Technical Details](#technical-details)

## Features

- **Automatic Tracking**: Records AI-authored lines via Claude Code hooks
- **Accurate Duplicate Handling**: Correctly counts duplicate lines (e.g., common boilerplate like `Args:`, `Returns:`, `try:`) across multiple methods
- **Format Attribution Preservation**: Maintains AI attribution through formatting changes (spotlessApply, prettier, black, etc.)
- **Git Diff-Based**: Only counts changes in your branch (not pre-existing code)
- **Commit Stats**: Automatically appends contribution stats to commit messages
- **Fast**: File-first hash structure for 50x faster lookups
- **MR Title Stats**: Optionally updates GitLab MR titles with compact `[AI: X%]` tag on push (disabled by default)
- **MR Description Stats**: Optionally includes detailed contribution breakdown in MR descriptions with preserved existing content (disabled by default, independent of title update)
- **MR Auto-Creation**: Optionally creates draft MRs automatically on first push when no MR exists (disabled by default)
- **MR AI Labeling**: Optionally attaches a GitLab label (`AI:85%`) reflecting the AI contribution percentage; auto-updates on subsequent pushes (disabled by default)
- **Automatic Housekeeping**: Cleans up stale tracking files for deleted/merged branches
- **Configurable**: Support for multiple base branches, file extensions, and logging

## Prerequisites

Before using the AI Contribution Tracker, ensure the following requirements are met:

- **Git CLI**: Required for all tracking functionality
- **Git Working Directory**: Must be in a git repository
- **Feature Branch**: Create a feature branch before making changes - tracking does not work on base branches (main, master, develop)
- **glab CLI** (Optional): Required only for MR features (title updates, description stats, auto-creation)
  - Install: Follow instructions at [glab installation](https://gitlab.com/gitlab-org/cli#installation)
  - Authenticate: Run `glab auth login` after installation

**Important**: AI contributions are only tracked when using Claude Code's `Write` and `Edit` tools. Manual edits, bash commands, or other modification methods are counted as human contributions.

## How It Works

1. **Capture Hook** (PostToolUse Write/Edit): Records hashes of AI-written lines
2. **Format Pre Hook** (PreToolUse Bash): Captures file state before formatting commands
3. **Format Post Hook** (PostToolUse Bash): Updates AI attribution after formatting using token-based matching
4. **Inject Hook** (PostToolUse Bash): On commit, calculates stats and amends commit message
5. **Housekeeping**: Automatically cleans up stale tracking files during inject hook
6. **MR Update Hook** (PostToolUse Bash): On push, independently applies any enabled MR features — title tag, description stats, `AI:X%` label, and/or draft MR auto-creation (all opt-in, each flag independent)
7. **Git Diff Analysis**: Uses `git diff <merge-base> HEAD` to count only branch changes

**Format Attribution Preservation**:
- Automatically detects formatting commands: `spotlessApply`, `prettier`, `black`, `eslint --fix`, `gofmt`, `rustfmt`, `clang-format`
- Captures file state before formatting (PreToolUse hook)
- Compares formatted state using token-based matching to preserve AI line attribution
- Updates tracking data to reflect formatting changes without losing AI contribution data

**Merge & Rebase Handling**:
- merge_base is recalculated fresh on every commit (never cached)
- After `git merge main`: merge_base advances to tip of main, so `git diff` excludes main's changes
- After `git rebase main`: merge_base advances to rebase point, same correct behavior
- AI line hashes are content-based, so they survive merge and rebase unchanged
- Files only modified on main (not in `files_tracked`) are automatically excluded from stats

**Important Limitations**:
- AI contributions are tracked only for `Write` and `Edit` tool operations. Manual edits, bash commands, or other modification methods are counted as human contributions.
- Direct commits to base branches (main, master, develop) are not tracked. Create a feature branch to track contributions.

## Format Attribution Details

The format attribution system preserves AI contribution tracking through code formatting:

**Supported Formatters:**
- Java/Kotlin: `spotlessApply`
- JavaScript/TypeScript: `prettier`, `eslint --fix`
- Python: `black`
- Go: `gofmt`
- Rust: `rustfmt`
- C/C++: `clang-format`

**How It Works:**
1. **Pre-format snapshot**: Captures file content and AI line hashes before formatting
2. **Token normalization**: Extracts semantic tokens (identifiers, keywords, literals) from each line
3. **Post-format matching**: Uses token-based similarity to match formatted lines with original lines
4. **Attribution update**: Updates tracking data with new line hashes while preserving AI attribution

**Example:**
```python
# Before formatting (AI-authored)
def calculate(x,y):
    return x+y

# After black formatting
def calculate(x, y):
    return x + y
```
The system recognizes that despite whitespace changes, the semantic content matches and preserves AI attribution for all three lines.

**Temporary Files:**
- Snapshots stored in `.claude/format-snapshot-{pid}.json` during formatting
- Automatically cleaned up after post-format processing
- Contains pre-format file content and AI line hashes

## Installation

Install at `~/.claude/hooks/ai-contribution-tracker/`

Hooks are configured in `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"command": "python3 $HOME/.claude/hooks/ai-contribution-tracker/ai-tracker-format-pre.py"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{"command": "python3 $HOME/.claude/hooks/ai-contribution-tracker/ai-tracker-capture.py"}]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {"command": "python3 $HOME/.claude/hooks/ai-contribution-tracker/ai-tracker-inject.py"},
          {"command": "python3 $HOME/.claude/hooks/ai-contribution-tracker/ai-tracker-mr-update.py"},
          {"command": "python3 $HOME/.claude/hooks/ai-contribution-tracker/ai-tracker-format-post.py"}
        ]
      }
    ]
  }
}
```

**Hook Execution Order:**
1. **PreToolUse Bash** → `ai-tracker-format-pre.py` (captures state before formatting)
2. **PostToolUse Write/Edit** → `ai-tracker-capture.py` (records AI-written lines)
3. **PostToolUse Bash** → `ai-tracker-inject.py` (injects stats on commit), then `ai-tracker-mr-update.py` (updates MR title on push), then `ai-tracker-format-post.py` (updates attribution after formatting)

## Configuration

Configuration and log files are stored at a fixed global location:

```
$HOME/.claude/ai-contribution-tracker/config.json
$HOME/.claude/ai-contribution-tracker/ai-tracker.log
```

The directory is created automatically if it doesn't exist. This path is stable regardless of how the tracker is installed (direct or marketplace plugin).

**Version Prefix**: Hook output messages include the plugin version in the prefix (e.g., `[ai-tracker:0.0.14]`). When installed as a marketplace plugin, the version is read from `.claude-plugin/plugin.json` via `CLAUDE_PLUGIN_ROOT`. For direct installations, the prefix shows `[ai-tracker:dev]`.

Edit `config.json` to customize:

```json
{
  "enabled": true,
  "base_branches": ["main", "master", "develop"],
  "tracked_extensions": [
    ".java", ".kt", ".py", ".js", ".ts",
    ".yml", ".json", ".sql"
  ],
  "enable_logging": true,
  "log_file": "ai-tracker.log",
  "mr": {
    "titleUpdateEnabled": false,
    "descriptionUpdateEnabled": false,
    "autoCreationEnabled": false,
    "labelingEnabled": false
  },
  "housekeeping": {
    "enabled": true,
    "staleDaysThreshold": 7,
    "maxFilesPerRun": 5
  }
}
```

**Options:**
- `enabled` - Master on/off switch for entire feature
- `base_branches` - Priority-ordered list of base branches to try (also used for MR target resolution)
- `tracked_extensions` - File types to track
- `enable_logging` - Enable/disable debug logging
- `log_file` - Log file name
- `mr.titleUpdateEnabled` - Append/update `[AI: X%]` tag in existing MR titles on push (default: false)
- `mr.descriptionUpdateEnabled` - Append/update AI stats section in existing MR descriptions on push (default: false)
- `mr.autoCreationEnabled` - Auto-create draft MR on first push when none exists (default: false)
- `mr.labelingEnabled` - Attach/update an `AI:X%` GitLab label on the MR on every push (default: false)
- `housekeeping.enabled` - Automatically clean up stale tracking files (default: true)
- `housekeeping.staleDaysThreshold` - Days before a tracking file is considered stale (default: 7)
- `housekeeping.maxFilesPerRun` - Maximum files to process per commit for performance (default: 5)

## MR Title Stats, Auto-Creation & Labeling

The tracker provides four independent GitLab MR features, each controlled by its own flag. Any combination can be enabled simultaneously; enabling one does not activate the others.

### 1. MR Title Updates

Automatically appends a compact `[AI: X%]` tag to GitLab MR titles after `git push`. The tag shows the overall AI contribution percentage for the branch and is updated on every push.

**Example:** `Add authentication feature` → `Add authentication feature [AI: 85%]`

**How it works:**
1. Runs after every `git push` (PostToolUse Bash hook)
2. Queries `glab mr list --source-branch <branch>` to find the MR
3. If MR found, reads pre-calculated stats from tracking file
4. Appends or replaces the `[AI: X%]` tag in the title
5. Skips silently if no MR exists, glab is unavailable, or feature is disabled

**Behavior:**
- Tag is always appended at the end of the title
- Existing `[AI: X%]` tag is replaced (no duplicates)
- Tag push (`--tags`) is ignored
- All errors are logged but never block the push

### 2. MR Description Stats

Independently appends detailed contribution statistics to GitLab MR descriptions on every push. Controlled by `descriptionUpdateEnabled` — can be enabled without enabling title updates. Preserves all existing description content.

**Example MR Description:**
```markdown
## Existing User-Written Content

This MR implements authentication...

## AI Contribution Stats

Overall: +150 -50
  AI: 170 lines (85.0%)
    +140 (93.3%)
    -30 (60.0%)
  Human: 30 lines (15.0%)
    +10 (6.7%)
    -20 (40.0%)
```


**How it works:**
1. Runs after every `git push` (PostToolUse Bash hook)
2. Fetches current MR description
3. Strips existing stats section if present
4. Appends new stats section with latest data
5. Preserves all other description content (user notes, checklists, etc.)

**Behavior:**
- Stats section uses markdown heading `## AI Contribution Stats` with code fence
- Existing stats section is replaced (identified by heading + code fence pattern)
- All other description content is preserved unchanged
- Runs independently of title updates — either or both can be enabled
- All errors are logged but never block the push

### 3. MR Auto-Creation

Automatically creates a draft MR on first `git push` when no MR exists for the branch. The MR title is derived from the branch name. AI stats are added to the title, description, and/or label only when the respective flags (`titleUpdateEnabled`, `descriptionUpdateEnabled`, `labelingEnabled`) are also enabled.

**Branch Title Derivation:**
- Extracts Jira ticket (case-insensitive, uppercased)
- Strips prefix before first `/` delimiter
- Humanizes remaining text (replaces `-`/`_` with spaces, capitalizes first word)
- Appends `[AI: X%]` tag if tracking stats available

**Examples** (with `titleUpdateEnabled: true`):
- `feature/PROJ-12345-add-login` → `PROJ-12345 Add login [AI: 90%]`
- `bugfix/proj-999-fix-auth` → `PROJ-999 Fix auth [AI: 75%]`
- `feature/some-feature` → `Some feature` (no stats yet)

With `titleUpdateEnabled: false`: title is always the plain derived name with no AI tag.

**Target Branch Resolution:**
- Traverses `base_branches` list from config (e.g., `["main", "master", "develop"]`)
- Checks each branch in order (tries local then `origin/` remote)
- Uses first existing branch as MR target

**How it works:**
1. Runs after every `git push` (PostToolUse Bash hook)
2. Queries `glab mr list --source-branch <branch>` to check if MR exists
3. If no MR found and auto-creation enabled:
   - Resolves target branch from config
   - Derives title from branch name
   - Appends `[AI: X%]` tag to title if `titleUpdateEnabled` and stats available
   - Includes stats in description if `descriptionUpdateEnabled` and stats available
   - Attaches `AI:X%` label if `labelingEnabled` and stats available
   - Creates draft MR via `glab mr create --draft`

**Behavior:**
- MR is always created in draft state regardless of which flags are set
- MR created even without tracking stats (plain title, empty description, no label)
- Each AI enrichment (title tag, description, label) requires its own flag to be enabled
- Target branch selected automatically from config
- All errors are logged but never block the push

### 4. MR AI Labeling

Automatically attaches a GitLab label reflecting the integer AI contribution percentage (e.g., `AI:85%`) to the MR on every push. On subsequent pushes, the old label is replaced if the percentage changed, or skipped if it is the same.

**Example:** MR gets label `AI:85%`. Next push with 90% AI → label replaced with `AI:90%`.

**How it works:**
1. Runs after every `git push` alongside title/description update
2. Reads pre-calculated stats from tracking file
3. Computes integer-rounded percentage label (`AI:X%`)
4. Scans current MR labels for any existing `AI:*%` label
5. If none found → adds new label
6. If found and different → removes old, adds new
7. If found and same → no-op

**Behavior:**
- Label format: `AI:85%` (integer, no decimals)
- GitLab auto-creates the label on first use (no manual label creation needed)
- Non-AI labels on the MR are never touched
- On draft MR creation: label attached directly via `glab mr create --label`
- All errors are logged but never block the push

### Configuration

**All features disabled by default.** To enable, add to `config.json`:

```json
{
  "mr": {
    "titleUpdateEnabled": true,
    "descriptionUpdateEnabled": true,
    "autoCreationEnabled": false,
    "labelingEnabled": true
  }
}
```

**Options:**
- `titleUpdateEnabled` - Append/update `[AI: X%]` tag in existing MR titles on push
- `descriptionUpdateEnabled` - Append/update AI stats section in existing MR descriptions on push
- `autoCreationEnabled` - Auto-create draft MR on first push when none exists
- `labelingEnabled` - Attach/update an `AI:X%` GitLab label on the MR on every push

All four flags are **fully independent** — any combination can be enabled.

**Prerequisites:**
- `glab` CLI installed and authenticated (`glab auth login`)
- For title/description updates: An open MR must already exist
- For auto-creation: No MR should exist (otherwise title/description update runs instead)
- For labeling: Works with both existing and auto-created MRs

**Notes:**
- Title and description updates are separate — enabling one does not enable the other
- Existing description content is always preserved — only the `## AI Contribution Stats` section is updated
- Stats section can be manually removed from description without affecting future updates
- When all four flags are off, the hook exits immediately without calling `glab`

## Automatic Housekeeping

The tracker automatically cleans up stale tracking files for branches that have been deleted or merged.

**How it works:**
1. Runs during inject hook (after every commit)
2. Selects up to 5 oldest tracking files (by `last_updated` timestamp)
3. For each file:
   - Checks if branch exists locally
   - Checks file age against threshold (default: 7 days)
   - Deletes file if branch doesn't exist locally AND file is older than threshold

**Behavior:**
- Current branch file never deleted
- Files for existing local branches kept
- Processes max 5 files per commit (incremental cleanup)
- Handles corrupted JSON gracefully
- Falls back to file mtime if `last_updated` missing
- Errors logged but never block commit

**Configuration:**
```json
{
  "housekeeping": {
    "enabled": true,
    "staleDaysThreshold": 7,
    "maxFilesPerRun": 5
  }
}
```

## Example

**Scenario:**
- File has 100 lines on main branch
- Create feature branch
- AI adds 5 lines
- Human adds 1 line

**Commit Message:**
```
Feature: Add new functionality

AI contribution: 5 lines (83.3%), Human: 1 lines (16.7%)
```

**With git diff tracking**: Shows 5 AI / 6 changes = 83.3% ✅

## Why Stats Differ from Git Diff

The AI tracker statistics may differ from `git diff --stat` output for the following reasons:

### 1. Blank Lines and Whitespace are Excluded

The tracker **skips blank lines and whitespace-only lines** when counting changes. This provides a more accurate measure of semantic code contributions.

**Example:**
```python
# Git diff shows +5 lines
def example():

    x = 1
    y = 2

    return x + y

# AI tracker counts only 3 lines (skips the 2 blank lines)
```

**Implementation:** Lines are normalized using `line.strip()`, and empty results are not counted.

### 2. Only Tracked File Extensions are Counted

The tracker **only counts files with configured extensions** (see `tracked_extensions` in config.json). Other files are ignored even if they appear in the git diff.

**Default tracked extensions:**
- Code: `.java`, `.kt`, `.py`, `.js`, `.ts`, `.go`, `.rs`, `.c`, `.cpp`
- Config: `.yml`, `.yaml`, `.json`, `.xml`, `.properties`, `.sql`
- Scripts: `.sh`, `.bash`

**Example:**
```bash
$ git diff --stat
src/main.py     | 10 +++++
README.md       | 5 +++++
build.gradle    | 2 ++
image.png       | Bin 0 -> 1024 bytes

# AI tracker counts only tracked extensions:
# - main.py: 10 lines ✓
# - README.md: 0 lines (not in tracked_extensions) ✗
# - build.gradle: 0 lines (not in tracked_extensions) ✗
# - image.png: 0 lines (binary file) ✗
```

### 3. Only Files AI Has Touched are Counted

The tracker **only counts files in `files_tracked`** - files that AI has written or edited. If you manually edit a file or modify it outside of Claude Code Write/Edit tools, those changes are not included in the statistics.

**Example:**
```bash
$ git diff --stat
src/ai_created.py    | 10 +++++  # AI created via Write tool
src/manual_edit.py   | 5 +++++  # You edited manually

# AI tracker counts:
# - ai_created.py: 10 lines ✓ (in files_tracked)
# - manual_edit.py: 0 lines ✗ (not in files_tracked)
```

### 4. Leading/Trailing Whitespace is Normalized

Lines are compared after stripping leading and trailing whitespace. This means indentation changes or trailing spaces don't affect line counting.

**Example:**
```python
# Original (AI-written):
def foo():
    return 1

# After manual reindentation:
def foo():
        return 1

# AI tracker still recognizes "return 1" as the same line (both strip to "return 1")
```

### Summary

**Git diff counts:** All lines in all files (including blanks, binaries, and untracked extensions)

**AI tracker counts:** Non-blank lines in tracked file types that AI has touched via Write/Edit tools

This is by design to provide accurate attribution of **semantic code contributions** rather than raw line counts.

## Tracking Files

Per-branch tracking files are stored in `.claude/ai-tracking-{branch}.json`:

```json
{
  "branch": "feature/my-branch",
  "merge_base": "abc123...",
  "ai_line_hashes": {
    "src/main.py": ["hash1", "hash2", ...]
  },
  "files_tracked": ["src/main.py"],
  "stats": {
    "ai_lines": 42,
    "human_lines": 158,
    "total_lines": 200,
    "ai_percentage": 21.0
  }
}
```

**Note**: Tracking files must be deleted manually if you want to reset stats or recalculate from scratch. Delete `.claude/ai-tracking-{branch}.json` to start fresh.

## Disabling

**Permanently:**
```json
{
  "enabled": false
}
```

## Structure

- `ai-tracker-capture.py` - Capture hook entry point (PostToolUse Write/Edit)
- `ai-tracker-inject.py` - Inject hook entry point (PostToolUse Bash - commits)
- `ai-tracker-mr-update.py` - MR update hook entry point (PostToolUse Bash - push)
- `ai-tracker-format-pre.py` - Format pre-hook entry point (PreToolUse Bash)
- `ai-tracker-format-post.py` - Format post-hook entry point (PostToolUse Bash - formatting)
- `config.json` - Configuration
- `domain/` - Business logic (LineHasher, Diff, TrackingData, ContributionStats, FormatSnapshot, TokenNormalizer)
- `infrastructure/` - Git, GitLab, and file operations (GitRepository, GlabRepository, TrackingRepository, Configuration)
- `services/` - Workflow coordination (CaptureService, InjectService, MrService, StatsCalculator, FormatSnapshotService, FormatTrackerService)
- `tests/` - Unit tests
- `ai-tracker.log` - Debug log (if logging enabled)

## Testing

Run all tests with pytest:

```bash
cd ~/.claude/hooks/ai-contribution-tracker
python3 -m pytest tests/ -v
```

**Test Coverage:**
- Unit tests for each service and domain model
- Integration tests for end-to-end workflows
- Migration tests for backward compatibility

**Run specific test file:**
```bash
python3 -m pytest tests/test_capture_service.py -v
```

**Run with coverage:**
```bash
python3 -m pytest tests/ --cov=. --cov-report=html
```

## Technical Details

**Performance:**
- File-first hash structure: O(n) where n = hashes in file (not all hashes)
- Lazy scanning: Only at commit time (no overhead on Write/Edit)

**Accuracy:**
- Git diff-based: Only counts lines added/modified in branch
- Merge-base recalculation: Fresh on every commit, correct after merge/rebase
- Hash-based tracking: Content-based (survives copy/paste)
- Count-based attribution: Correctly handles duplicate lines (e.g., multiple methods with same boilerplate)
- Occurrence matching: If a line appears N times in tracking and M times in diff, counts min(N,M) as AI
- Tracks only Write/Edit operations: Other modification methods counted as human
