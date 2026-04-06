---
name: msv-tool-permission-refiner
description: This skill should be used when the user asks to "audit tool permissions", "refine permissions from log", "check what tools need permissions", "analyze tool usage permissions", "permission audit", "run tool-permission-refiner", "what tools are unmatched", "tighten permissions", or wants to derive permission rules from ~/.claude/feedback-loop/tool-detector.jsonl into settings.json allow/ask/deny lists. Cross-references real tool usage data against all permission layers and applies security-first, principle-of-least-privilege suggestions.
version: 1.0.0
allowed-tools: Read, Grep, Glob, Edit
---

# Tool Permission Refiner

## Purpose

Analyze `~/.claude/feedback-loop/tool-detector.jsonl` to find what tools and commands are actually used, cross-reference against all permission layers (user / local / project), and propose pragmatic changes to `allow`, `ask`, and `deny` arrays. Default stance: allow reads on non-secret paths and writes to expected project/work paths — restrict only sensitive targets, credentials, and genuinely destructive operations.

## Target Files (in precedence order)

1. `~/.claude/settings.json` — user-level (primary target)
2. `~/.claude/settings.local.json` — local overrides
3. `.claude/settings.json` in CWD — project-level (if exists)

Precedence: `deny > ask > allow`, `project > local > user`. Suggestions go to the lowest (most specific) layer that makes sense.

## Core Workflow

### Phase 1: Parse Log

```bash
jq -r '[.timestamp, .tool, .command] | @tsv' ~/.claude/feedback-loop/tool-detector.jsonl | sort
```

Group entries by:
- `tool` field (Bash, Read, Edit, Write, Glob, Grep, ToolSearch, LSP, Agent, etc.)
- For Bash: extract the leading sub-command token from `.command` (e.g. `git`, `gradle`, `jq`, `aws`)

Count occurrences per pattern. Every occurrence counts — unlike failure analysis, a single tool use is enough to warrant a permission review.

Build usage inventory: `{ tool, pattern, count, example_commands[] }`.

### Phase 2: Load All Permission Layers

Read each settings file and extract `permissions.allow`, `permissions.ask`, `permissions.deny`:

```bash
jq '.permissions' ~/.claude/settings.json
jq '.permissions' ~/.claude/settings.local.json 2>/dev/null
jq '.permissions' .claude/settings.json 2>/dev/null
```

Build a flat rule map with layer tags. For each log pattern, attempt glob-style match against all rules across all layers. Record: matched rule, layer, bucket (allow/ask/deny).

### Phase 3: Gap & Security Analysis

Classify each log pattern:

| Classification | Severity | Meaning |
|---|---|---|
| `ADD_TO_ALLOW` | 🟢 | Unmatched, safe read-only op — add to `allow` for convenience |
| `UNMATCHED` | 🟡 | Used but no rule — currently falls to `defaultMode`; needs explicit placement |
| `MOVE_TO_ASK` | 🟠 | Currently in `allow` but command can modify state, exec scripts, or call network |
| `MOVE_TO_DENY` | 🔴 | Touches credentials, secrets, keys, or is irreversibly destructive |
| `ALREADY_COVERED` | ⚪ | Matched by existing rule — skip (count only in summary) |
| `OVERLY_PERMISSIVE` | ⚠️ | Rule in `allow` that was never seen in log and has dangerous potential |

**Classification rules (apply in this order):**

1. **`MOVE_TO_DENY`**: Anything touching `~/.aws`, `~/.ssh`, `*.key`, `*.pem`, `*.env`, secrets dirs; package publishing (`npm publish`, `pip upload`); force-push (`git push --force`), hard-reset, `rm -rf`; privilege escalation (`sudo`, `su`); pushing secrets or credentials to any remote.

2. **`MOVE_TO_ASK`** — applies to any operation that is **remote** or **synchronizes with remote** (excluding git — see Git Special Group below):
   - **Remote reads**: `curl`, `wget`, `glab api`, `gh api`, `aws * get*`, `kubectl get`, MCP tools that call external APIs. Risk: response may contain injected content.
   - **Remote mutations**: deploys, `kubectl apply/scale`, `terraform apply`, `helm install/upgrade`, `aws * create/update/put`, migrations, any CLI with verbs like `sync`, `deploy`, `publish`, `upload`, `send`.
   - Package installs: `brew install`, `pip install`, `npm install` — network + filesystem mutation.
   - Exec into remote systems: `ssh`, `kubectl exec`, `docker exec`.

3. **`ADD_TO_ALLOW`**:
   - `Read`, `Glob`, `Grep` on **any non-secret path** — always allow.
   - `Edit` and `Write` to **expected project/work paths** (source files, configs, `.claude/`, build output) — allow if target is not a secret/credential file.
   - Pure local read-only `Bash`: git log/status/diff/show/blame/branch/tag/remote (no network), ls, jq, head, tail, wc, cat, echo, test, find, grep; `LSP`; `Agent`; `mcp__sequentialthinking__*`, `mcp__context7__*`.

4. **`GIT_SPECIAL_GROUP`** — git is treated exclusively. Do not fold git commands into generic remote/local rules. Analyze each git sub-command on its own merit and present them as a dedicated block in the report:

   | Sub-command | Default suggestion | Rationale |
   |---|---|---|
   | `git log`, `git status`, `git diff`, `git show`, `git blame`, `git branch`, `git tag`, `git remote -v` | `allow` | Pure local read — no side effects |
   | `git fetch` | `allow` | Downloads remote refs locally, no local branch changes; safe and essential for staying current |
   | `git pull` | `allow` (with note) | Merges remote into local — safe in most workflows; note that it modifies working tree |
   | `git stash`, `git stash pop` | `allow` | Local-only; fundamental workflow op, no remote contact |
   | `git checkout`, `git switch` | `CONSIDER_ALLOW` | Modifies local state; see tradeoff below |
   | `git merge`, `git rebase` | `CONSIDER_ALLOW` | Modifies local history; user should decide |
   | `git add`, `git commit` | `ask` | Stages/records changes; user should confirm intent |
   | `git push` | `ask` | Sends local commits to remote; always needs confirmation |
   | `git push --force`, `git push -f` | `deny` | Irreversible remote history rewrite |
   | `git reset --hard` | `ask` (or `deny`) | Discards local commits/changes; destructive |
   | `git clean -f` | `ask` | Deletes untracked files |
   | `git clone` | `ask` | Creates new local repo from remote; scope/target unclear without context |

   When git commands appear in the log, group all of them into a `--- GIT OPERATIONS ---` block in the report. Show current placement (allow/ask/deny/unmatched) alongside the suggested placement. If a command is already in the right bucket, mark ⚪ and skip. Only surface gaps and misplacements.

   **Important**: commands that start with `cd ... && git ...` do NOT match `Bash(git * ...)` rules — flag this bypass explicitly if seen in the log.

5. **`CONSIDER_ALLOW` (high-frequency safe local op)** — special nuance for well-known ops:
   Some local ops (e.g. `git checkout`, `git stash`, `git merge`, `git rebase`) modify local state but are fundamental daily-driver commands, extremely well-documented, and rarely harmful in isolation. If the log shows these used frequently across sessions, do NOT silently suggest `ask` — instead present a named tradeoff to the user:
   ```
   🔵 CONSIDER_ALLOW — high-frequency local op  [user ~/.claude/settings.json]
   Pattern:   "Bash(git checkout *)"
   Seen:      N times
   Tradeoff:
     🟢 Allowing avoids constant prompts; git checkout is safe in the vast majority of uses
     🔴 Can overwrite uncommitted local changes if used carelessly (git checkout -- <file>)
   Recommendation: Allow — but ensure deny rules exist for destructive variants
   Action:    Add to allow[] ?  (ask user to decide)
   ```
   Let the user decide. Do not default to `ask` for these without surfacing the tradeoff.

5. **`UNMATCHED`** (no clear category): flag with a recommendation (allow / ask / deny) and reasoning.

6. **`OVERLY_PERMISSIVE`**: scan `allow[]` for rules that: (a) have no matching log entry in recent history AND (b) match patterns known to be dangerous (remote mutation, credential access, destructive exec, package management).

**Remote operation detection heuristic** — classify a Bash command as "remote" if it:
- Contains a URL, hostname, IP, or remote ref (e.g. `origin`, `upstream`)
- Uses a CLI known to be network-bound by default: `curl`, `wget`, `git fetch/pull/push/clone`, `glab`, `gh`, `aws`, `kubectl`, `helm`, `terraform`, `ssh`, `scp`, `rsync --remote`, `docker pull/push`
- Contains verbs: `fetch`, `pull`, `push`, `sync`, `deploy`, `publish`, `upload`, `download`, `clone`, `checkout` (when targeting a remote ref)

### Phase 4: Present and Apply

Present suggestions in this order: `MOVE_TO_DENY` → `MOVE_TO_ASK` → `UNMATCHED` → `ADD_TO_ALLOW` → `CONSIDER_ALLOW` → `OVERLY_PERMISSIVE` → `--- GIT OPERATIONS (special group) ---`.

**Output format:**

```
=== TOOL PERMISSION REFINER REPORT ===

Scanned: N log entries | N unique patterns | N already covered (⚪)

--- SUGGESTIONS ---

1. 🔴 MOVE_TO_DENY  [user ~/.claude/settings.json]
   Pattern:   "Bash(some-command *)"
   Seen:      3 times — e.g. "some-command ~/.aws/credentials"
   Rationale: Accesses credential files; irreversible risk
   Action:    Remove from allow[] → add to deny[]

2. 🟠 MOVE_TO_ASK  [user ~/.claude/settings.json]
   Pattern:   "Bash(npm run *)"
   Seen:      5 times — e.g. "npm run build", "npm run deploy"
   Rationale: Can execute arbitrary scripts including deploy hooks
   Action:    Remove from allow[] → add to ask[]

3. 🟡 UNMATCHED — recommend ask  [user ~/.claude/settings.json]
   Pattern:   "Bash(python3 *)"
   Seen:      8 times — e.g. "python3 script.py", "python3 -c ..."
   Rationale: No rule; falls to defaultMode; can execute arbitrary code
   Action:    Add to ask[]

4. 🟢 ADD_TO_ALLOW  [user ~/.claude/settings.json]
   Pattern:   "Bash(git --no-pager *)"
   Seen:      12 times — e.g. "git --no-pager log", "git --no-pager diff"
   Rationale: Read-only git operation; currently unmatched; safe to auto-allow
   Action:    Add to allow[]

5. ⚠️ OVERLY_PERMISSIVE  [user ~/.claude/settings.json]
   Pattern:   "Bash(sed *)"  (in allow[])
   Seen:      0 times in log
   Rationale: Never used; `sed` with -i can silently overwrite files (already denied via sed -i*, but base pattern is broad)
   Action:    Consider narrowing or moving to ask[]

--- ALREADY COVERED: N patterns ⚪ ---
Bash(git log *), Bash(git * status), Read(**/*.md), Glob, Grep, LSP ...

Apply which suggestions? Enter numbers (e.g. 1,3,4), "all", or "none"
```

After user selects:
1. Apply all approved changes to the correct settings file using `Edit` tool
2. All changes to the same file in a single atomic `Edit` call
3. Maintain JSON validity — preserve formatting style of the existing file
4. Confirm applied changes with a brief summary

## Validation Checklist

Before presenting suggestions:
- ✓ Pattern backed by actual log entry (or explicitly flagged as zero-occurrence for OVERLY_PERMISSIVE)
- ✓ Proposed rule does not duplicate an existing rule verbatim or semantically
- ✓ `deny` takes precedence — never suggest adding to `allow` a pattern already in `deny`
- ✓ Security-first: when classification is ambiguous, prefer the more restrictive bucket
- ✓ Show both old and new state for MOVE_TO_* suggestions
- ✓ Each suggestion includes the target layer (user/local/project)
- ✓ Applied JSON remains valid — run `jq . <file>` mentally before editing
