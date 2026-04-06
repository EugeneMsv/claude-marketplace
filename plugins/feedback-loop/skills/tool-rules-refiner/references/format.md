# Tools.md Format Reference

## Target File Structure

`~/.claude/guides/Tools.md` uses this layout:

```markdown
# Tools usage

## Required for Every Task:
...

## Guidelines:
...

## [ToolName]

### [Sub-group / Sub-command]
- RULE ONE
- RULE TWO

### [Another Sub-group]
- RULE

## [AnotherTool]
...
```

**Tool section order**: Required → Guidelines → Research → Execution → then specific tools alphabetically (Bash, Edit, Glob, Grep, Read, Write, ...)

**Sub-groups for Bash** (use these labels consistently):
- `Git` — all git commands
- `Gradle` — ./gradlew commands
- `jq` — jq usage
- `File Operations` — cat, echo, find, etc.
- `General` — shell patterns not fitting above

**Rule style:**
```
- Stage specific files only — not `git add .`
- Use `git --no-pager <cmd>` for clean output
- Use `Grep` tool for content search — not `grep`/`rg` in Bash
- Use Write tool for file creation — not `echo > file`
- NEVER `git reset --hard` without confirming no uncommitted work (destructive → OK for NEVER)
```
Reserve `NEVER` for destructive or irreversible operations. Prefer positive action commands otherwise.

## Suggestion Output Format

Number every suggestion sequentially across all severity groups. The user will reference suggestions by number when approving/rejecting.

```markdown
## Suggested Rule Updates

### 1. 🔴 STRENGTHEN — [Tool] / [Sub-group]

**File:** `~/.claude/guides/Tools.md`
**Section:** `## Bash > ### Git`

**Old rule:**
`- Use git --no-pager for clean output`

**New rule:**
`- ALWAYS `git --no-pager <subcommand>` — global flag BEFORE subcommand`

**Evidence:** 3 failures: "git log" without --no-pager (2026-02-20, 2026-02-21, 2026-02-24)

---

### 2. 🟡 ADD — [Tool] / [Sub-group]

**File:** `~/.claude/guides/Tools.md`
**Section:** `## Bash > ### jq`

**Rule:**
`- NEVER pipe multi-line bash strings to jq — escape newlines first`

**Evidence:** 2 failures: jq parse error on unescaped newlines (2026-02-24 x2)

---

### 3. ⚠️ CONFLICT — [Tool] / [Sub-group]

**Proposed:** `- NEVER use pipes with jq`
**Conflicts with:** `CLAUDE.local.md` line 14: "Prefer simple piped commands"
**Resolution:** Narrow the rule scope: `- NEVER pipe unescaped multi-line strings to jq`
```

## Deduplication Logic

Before adding any rule, check:
1. `grep -i "<keyword>" ~/.claude/guides/Tools.md` — verbatim match?
2. Semantic check: does any existing rule cover the same failure mode?
3. Does `Workflows.md` already have a git rule covering this?

If duplicate found → skip silently (don't report as suggestion).
If semantically covered but weaker → STRENGTHEN instead of ADD.
