# AI Herald

Watches every AI write, then announces attribution stats at commit time — injecting AI vs human contribution percentages into git commit messages.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Features](#features)
- [Current Limitations](#current-limitations)
- [How It Works](#how-it-works)
- [Format Attribution Details](#format-attribution-details)
- [Installation](#installation)
- [Configuration](#configuration)
- [MR Title Stats, Auto-Creation & Labeling](#mr-title-stats-auto-creation--labeling)
- [Missed Commit Recovery](#missed-commit-recovery)
- [Automatic Housekeeping](#automatic-housekeeping)
- [Example](#example)
- [Tracking Files](#tracking-files)
- [Disabling](#disabling)
- [Structure](#structure)
- [Testing](#testing)
- [Technical Details](#technical-details)

## Prerequisites

Before using AI Herald, ensure the following requirements are met:

- **Git CLI**: Required for all tracking functionality
- **Git Working Directory**: Must be in a git repository
- **Feature Branch**: Must be created **before making any file changes**. Tracking is branch-scoped — any contributions made before switching to a feature branch will not be counted and cannot be recovered.
- **glab CLI** (Optional): Required only for MR features (title updates, description stats, auto-creation)
  - Install: Follow instructions at [glab installation](https://gitlab.com/gitlab-org/cli#installation)
  - Authenticate: Run `glab auth login` after installation

> **Important**: Only changes made via Claude Code's `Write` and `Edit` tools (sometimes referred to as `Update` by Claude Code) are counted as AI contributions for line additions.
> File deletions via `rm`, `git rm`, or `unlink` Bash commands are also counted as AI contributions — all removed lines from the deleted file are attributed to AI.
> Any other changes made outside Claude Code, or through any other Claude Code tool, are counted as human contributions.

## Features

- **Automatic Tracking**: Records AI-authored lines via Claude Code hooks
- **Accurate Duplicate Handling**: Correctly counts duplicate lines (e.g., common boilerplate like `Args:`, `Returns:`, `try:`) across multiple methods
- **Format Attribution Preservation**: Maintains AI attribution through formatting changes (spotlessApply, prettier, ruff, etc.)
- **Git Diff-Based**: Only counts changes in your branch (not pre-existing code)
- **Commit Stats**: Automatically appends contribution stats to commit messages
- **Fast**: File-first hash structure for 50x faster lookups
- **MR Title Stats**: Optionally updates GitLab MR titles with compact `[AI: X%]` tag on push (disabled by default)
- **MR Description Stats**: Optionally includes detailed contribution breakdown in MR descriptions with preserved existing content (disabled by default, independent of title update)
- **MR Auto-Creation**: Optionally creates draft MRs automatically on first push when no MR exists (disabled by default)
- **MR AI Labeling**: Optionally attaches a GitLab label (`AI:85%`) reflecting the AI contribution percentage; auto-updates on subsequent pushes (disabled by default)
- **Missed Commit Recovery**: Automatically recovers AI stats injection for commits made inside chained commands that partially failed (e.g. `git add && git commit && git push` where push fails)
- **Bash Deletion Tracking**: When AI runs `rm`, `git rm`, or `unlink` via the Bash tool, all removed lines from the deleted file are attributed to AI automatically
- **Automatic Housekeeping**: Cleans up stale tracking files for deleted/merged branches
- **Code-Gen Exclusion**: Files matching configurable Ant-style glob patterns (e.g. `**/generated/**`) are tracked separately as Code-Gen and excluded from AI/Human percentages
- **Configurable**: Support for multiple base branches, file extensions, and logging

## Current Limitations

> These are known constraints of the current implementation. Understanding them helps avoid
> surprises with contribution percentages.

- **Tool-scoped attribution for additions**: Only `Write` and `Edit` tool calls are captured as AI contributions for line additions. File deletions via `rm`, `git rm`, or `unlink` Bash commands are also tracked — all removed lines from such files are attributed to AI.
  Cherry-picks, patches, `git apply`, Bash-based file edits (other than deletions), and manual changes are all counted as human —
  even if the original code was AI-authored on another branch.
- **Feature branch must exist before any file changes**: Tracking is branch-scoped and starts from the
  moment the branch is created. Any AI-authored changes made before the branch was created are not
  recoverable.
- **Base branches are not tracked**: Commits directly to `main`, `master`, or `develop` are ignored.
  A feature branch is required.
- **Stats exclude blank lines and non-tracked file types**: The tracker skips blank/whitespace-only
  lines and files whose extension is not in `tracked_extensions`. This means tracker percentages will
  differ from raw `git diff --stat` output — see [Why Stats Differ from Git Diff](#why-stats-differ-from-git-diff).
- **No retroactive recalculation**: Tracking data is written at tool-call time. If you reset or delete
  a tracking file, past contributions cannot be reconstructed — only future Write/Edit operations will
  be counted.
- **MR features require glab and an open MR**: Title updates, description stats, and labeling only work
  when `glab` is installed, authenticated, and an MR already exists for the branch. Auto-creation can
  create the MR, but all other MR features are no-ops if no MR is found.
- **Format detection limited to configured formatters**: Only formatters listed in
  `format_detection.commands` are intercepted. Unlisted formatters will cause AI-attributed lines to
  be re-classified as human after formatting.
- **Format attribution is probabilistic, not exact**: After formatting, attribution is preserved using
  a token-based containment ratio — the algorithm asks "are the AI snapshot tokens still present in
  the file?" and applies an 80% threshold to decide. This is intentionally simple: a precise approach
  would require tracking exact line mappings across arbitrary N:M reformats, which is significantly
  more complex. Since formatting typically changes very little semantic content, the algorithm works
  correctly in the overwhelming majority of cases. However, edge cases exist — a formatting run that
  also introduces minor semantic changes (e.g. an import added automatically) may pass the threshold
  and over-attribute, or an unusually aggressive reformat may fall below it and lose attribution.
  Small discrepancies between tracked and actual AI contribution after formatting are a known
  trade-off.
- **Code-generated files are not attributed**: Files matching `code_generated_patterns` are excluded
  from both AI and human attribution entirely. Their line counts appear separately in commit stats
  under `Code-Gen:` but do not affect AI/Human percentages. This is intentional — generated files
  (protobuf outputs, GraphQL clients, build artifacts) skew percentages and should not be
  attributed to either contributor.
- **MR updates skipped when piped push returns exit code 1**: When `git push` runs as part of a
  chained command (e.g. `git add && git commit && git push`) and the overall command exits with code
  1 for any reason, Claude Code skips the PostToolUse event entirely — so the MR update hook never
  fires. For the commit step this is recoverable: the commit intent marker is recorded beforehand and
  the inject hook will amend the commit on the next successful push (see
  [Missed Commit Recovery](#missed-commit-recovery)). For the push step there is no equivalent
  recovery — if PostToolUse is skipped after a push, MR title updates, description stats, and label
  changes for that push are silently missed. Run the push as a standalone command to guarantee MR
  enrichment runs.

## How It Works

1. **Write Pre Hook** (PreToolUse Write): Snapshots existing file content before a Write overwrites it, enabling accurate AI-removed line tracking
2. **Capture Hook** (PostToolUse Write/Edit): Records AI-added line hashes; for Write operations, reads the pre-write snapshot to also record AI-removed lines
3. **Commit Pre Hook** (PreToolUse Bash): Before a `git commit`, records the current HEAD hash into the tracking file as a commit intent marker
4. **Bash Delete Hook** (PostToolUse Bash): Inspects each Bash command for `rm`/`git rm`/`unlink` patterns; cross-references against uncommitted git-deleted files; marks matched files as AI-deleted in tracking data so all their removed lines are attributed to AI at commit time
5. **Format Pre Hook** (PreToolUse Bash): Captures file state before formatting commands
6. **Format Post Hook** (PostToolUse Bash): Updates AI attribution after formatting using token-based matching
7. **Inject Hook** (PostToolUse Bash): On commit, calculates stats and amends commit message; on `git push`, checks for a pending commit intent and recovers any missed injection
8. **Housekeeping**: Automatically cleans up stale tracking files during inject hook
9. **MR Update Hook** (PostToolUse Bash): On push, independently applies any enabled MR features — title tag, description stats, `AI:X%` label, and/or draft MR auto-creation (all opt-in, each flag independent)
10. **Git Diff Analysis**: Uses `git diff <merge-base> HEAD` to count only branch changes

**Format Attribution Preservation**:

- Automatically detects formatting commands: `spotlessApply`, `prettier`, `ruff`, `eslint --fix`, `gofmt`, `rustfmt`, `clang-format`
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
- Python: `ruff`
- Go: `gofmt`
- Rust: `rustfmt`
- C/C++: `clang-format`

**How It Works:**

1. **Pre-format snapshot**: Captures file content and AI line hashes before formatting
2. **Token normalization**: Extracts semantic tokens (identifiers, keywords, literals) from each line
3. **Post-format matching**: Uses token-based containment ratio to match formatted lines with original lines — asks "are all AI snapshot tokens still present in the file?" rather than Jaccard similarity, making the score independent of file size
4. **Attribution update**: Updates tracking data with new line hashes while preserving AI attribution

**Example:**

```python
# Before formatting (AI-authored)
def calculate(x,y):
    return x+y

# After ruff formatting
def calculate(x, y):
    return x + y
```

The system recognizes that despite whitespace changes, the semantic content matches and preserves AI attribution for all three lines.

**Temporary Files:**

- Snapshots stored in `.claude/herald/formatting/{pid}.json` during formatting
- Automatically cleaned up after post-format processing
- Contains pre-format file content and AI line hashes

## Installation

**Preferred method**: Install via the Claude Code plugin marketplace. Once installed, hooks are registered automatically — no manual configuration needed.

For reference, the hooks registered by the plugin are:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-pre-writer.py"}]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-pre-formatter.py"},
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-pre-committer.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-change-captor.py"}]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-stats-injector.py"},
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-mr-injector.py"},
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-post-formatter.py"},
          {"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ai-herald/herald-bash-delete.py"}
        ]
      }
    ]
  }
}
```

**Hook Execution Order:**

1. **PreToolUse Bash** → `herald-pre-formatter.py` (captures state before formatting), `herald-pre-committer.py` (records commit intent before git commit)
2. **PostToolUse Write/Edit** → `herald-change-captor.py` (records AI-written lines)
3. **PostToolUse Bash** → `herald-stats-injector.py` (injects stats on commit, recovers missed injection on push), then `herald-mr-injector.py` (updates MR on push), then `herald-post-formatter.py` (updates attribution after formatting), then `herald-bash-delete.py` (marks deleted files as AI-deleted)

## Configuration

Configuration and log files are stored at a fixed global location:

```
$HOME/.claude/ai-herald/config.json
$HOME/.claude/ai-herald/ai-herald.log
```

The directory is created automatically if it doesn't exist. This path is stable regardless of how the herald is installed (direct or marketplace plugin).

**Version Prefix**: Hook output messages include the plugin version in the prefix (e.g., `[ai-herald:0.0.14]`). When installed as a marketplace plugin, the version is read from `.claude-plugin/plugin.json` via `CLAUDE_PLUGIN_ROOT`. For direct installations, the prefix shows `[ai-herald:dev]`.

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
  "log_file": "ai-herald.log",
  "code_generated_patterns": [
    "**/generated/**",
    "**/__generated__/**",
    "**/gen/**",
    "**/*.generated.ts",
    "**/*.generated.js",
    "**/*.generated.java",
    "**/*.pb.go",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/build/generated/**",
    "**/target/generated-sources/**"
  ],
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
- `code_generated_patterns` - List of Ant-style glob patterns for code-generated files; matched files are excluded from AI/Human percentages and reported separately under `Code-Gen:` in commit stats. Uses `fnmatch` matching where `*` matches any character including `/`. To disable exclusion entirely, set to `[]`. Default patterns cover protobuf outputs, GraphQL clients, and common build-tool generated directories.

  **Examples:**
  - `**/generated/**` — all files inside any `generated/` directory at any depth
  - `**/*.generated.ts` — TypeScript files ending in `.generated.ts`
  - `**/build/generated/**` — Gradle/Maven generated source output
  - `**/target/generated-sources/**` — Maven annotation processing output

  **Customization:**
  ```json
  {
    "code_generated_patterns": [
      "**/generated/**",
      "**/*.gen.go",
      "**/proto/out/**"
    ]
  }
  ```

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

## Missed Commit Recovery

When Claude runs a chained command like `git add && git commit && git push` and the push fails, Claude Code skips the PostToolUse event entirely — so the inject hook never fires and the commit is left without AI stats.

**How recovery works:**

1. Before any `git commit` runs, the Commit Pre Hook records the current HEAD hash into the branch tracking file as a "commit intent" marker.
2. If the push fails and PostToolUse is skipped, the marker stays in the tracking file.
3. The next time `git push` is run on that branch, the inject hook detects the marker, confirms that HEAD has changed (meaning the commit actually happened), and retroactively injects AI stats into that commit by amending it.
4. If the commit itself never completed (e.g. the commit step also failed), the marker is cleared without any action.

**Guard conditions** — recovery is skipped when:

- No tracking file exists for the branch
- No commit intent marker is present
- HEAD is unchanged since the marker was written (commit never happened)
- The commit message already contains stats (already injected via the normal path)

**Result:** No commit on a tracked branch is left without AI stats, regardless of whether it was part of a chained command that partially failed.

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
- Code-generated file updated (e.g. protobuf output regenerated): 20 lines

**Commit Message:**

```
Feature: Add new functionality

Overall: +26 -0
  AI: 5 lines (83.3%)
    +5 (100.0%)
    -0 (0.0%)
  Human: 1 lines (16.7%)
    +1 (100.0%)
    -0 (0.0%)
Tracked: .java, .py
  Code-Gen: 20 lines (excluded from AI/Human %)
    +20 -0
    Patterns: **/generated/**
```

**With git diff tracking**: Shows 5 AI / 6 non-generated changes = 83.3% ✅ (code-gen lines excluded from denominator)

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

### 3. Files Never Touched by AI Tools are Counted as Human

Files that AI never touched via `Write`/`Edit` are not in `files_tracked`, but their changed lines from
the git diff are still included in the stats — attributed entirely to human.

**Example:**

```bash
$ git diff --stat
src/ai_created.py    | 10 +++++  # AI created via Write tool
src/manual_edit.py   | 5 +++++  # You edited manually

# AI tracker counts:
# - ai_created.py: 10 lines, all AI ✓ (in files_tracked, hashes match)
# - manual_edit.py: 5 lines, all human ✓ (not in files_tracked → human by default)
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

### 5. Code-Generated Files are Excluded from AI/Human Totals

Files matching `code_generated_patterns` (protobuf outputs, GraphQL clients, build artifacts) are
counted separately under `Code-Gen:` in commit stats and are **never included** in the AI or human
totals. This prevents generated file churn from dominating the attribution percentage.

**Example:**

```bash
# Git diff shows 120 lines added:
# - 100 lines in src/generated/Client.java  (code-gen pattern match)
# - 20  lines in src/main/Service.java      (AI-written via Write tool)

# AI tracker reports:
# - AI: 20 lines (100%) — only Service.java counted
# - Code-Gen: 100 lines (excluded from AI/Human %)
```

### Summary

**Git diff counts:** All lines in all files (including blanks, binaries, and untracked extensions)

**AI tracker counts:** Non-blank lines in tracked file types — AI lines where Write/Edit hashes match, human lines for everything else, code-generated lines excluded from the AI/Human denominator

This is by design to provide accurate attribution of **semantic code contributions** rather than raw line counts.

## Tracking Files

Per-branch tracking files are stored in `.claude/herald/{branch}.json`:

```json
{
  "branch": "feature/my-branch",
  "merge_base": "abc123...",
  "ai_line_hashes": {
    "src/main.py": ["hash1", "hash2", ...]
  },
  "files_tracked": ["src/main.py"],
  "ai_deleted_files": ["src/old_module.py"],
  "stats": {
    "ai_lines": 42,
    "human_lines": 158,
    "total_lines": 200,
    "ai_percentage": 21.0
  }
}
```

`ai_deleted_files` lists files deleted by AI via `rm`/`git rm`/`unlink`. At commit time all their removed lines are attributed to AI without per-line hash matching.

**Note**: Tracking files must be deleted manually if you want to reset stats or recalculate from scratch. Delete `.claude/herald/{branch}.json` to start fresh.

## Disabling

**Permanently:**

```json
{
  "enabled": false
}
```

## Structure

- `herald-change-captor.py` - Capture hook entry point (PostToolUse Write/Edit)
- `herald-pre-committer.py` - Commit pre-hook entry point (PreToolUse Bash - records commit intent before git commit)
- `herald-stats-injector.py` - Inject hook entry point (PostToolUse Bash - injects stats on commit, recovers missed injection on push)
- `herald-mr-injector.py` - MR update hook entry point (PostToolUse Bash - push)
- `herald-pre-formatter.py` - Format pre-hook entry point (PreToolUse Bash)
- `herald-post-formatter.py` - Format post-hook entry point (PostToolUse Bash - formatting)
- `herald-pre-writer.py` - Write pre-hook entry point (PreToolUse Write - snapshots file before overwrite)
- `herald-bash-delete.py` - Bash file deletion hook entry point (PostToolUse Bash - detects `rm`/`git rm`/`unlink` and marks deleted files as AI-deleted)
- `config.json` - Configuration
- `domain/` - Business logic (LineHasher, Diff, TrackingData, ContributionStats, FormatSnapshot, TokenNormalizer, GeneratedCodeDetector)
- `infrastructure/` - Git, GitLab, and file operations (GitRepository, GlabRepository, TrackingRepository, Configuration)
- `services/` - Workflow coordination (CaptureService, InjectService, MrService, StatsCalculator, FormatSnapshotService, FormatTrackerService, DeletionTrackerService, DeletionTargetsDetector)
- `tests/` - Unit tests
- `ai-herald.log` - Debug log (if logging enabled)

## Testing

Run all tests with pytest:

```bash
cd ~/.claude/hooks/ai-herald
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

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Stats missing from commit message | Commit made outside Claude Code (e.g. terminal) | Use `git commit` inside a Claude Code session |
| AI% lower than expected | Changes made before branch was created | Always create branch before starting work |
| `[AI: X%]` not appearing in MR title | `titleUpdateEnabled` is false or no open MR | Enable flag in `config.json`; ensure MR exists |
| `glab` errors on push | Not authenticated | Run `glab auth login` |
