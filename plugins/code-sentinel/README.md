# code-sentinel

Expert code review and interactive GitLab MR comment resolution.

## Skills

### code-review

Trigger: "Review my feature branch", "PR review", "diff review"

Performs a senior engineer code review against `origin/main`:

1. Fetches all remote branches and generates a diff
2. Uses git worktrees to get full context for both branches
3. Identifies affected data flows with layer-by-layer ASCII diagrams (Web → Domain → Persistence → External)
4. Shows model/domain/DTO changes as a coloured diff tree (🔴 removed, 🟢 added, 🔵 changed, ⚪ unchanged)
5. Reviews each major change for logic, performance, security, SOLID violations, and test coverage
6. Produces a scored review (0–100) with copy-ready PR notes
7. Exports the full review to a markdown file in `.claude/`

**Rules:**
- Never posts to GitLab unless explicitly instructed
- Always compares against `origin/main` (not local main)
- Skips test files in detail, import-only changes, and formatting handled by spotlessApply

---

### mr-nitpick-sentinel

Trigger: "address MR comments", "review MR feedback", "handle reviewer comments"

Interactively resolves GitLab MR review comments one by one:

1. Detects current branch and finds the associated MR via `glab`
2. Fetches all discussions via the GitLab discussions API (handles >20 comments, unlike `glab mr view --comments`)
3. Enriches each inline comment with surrounding code context
4. Lets you select which comments to address
5. Launches Plan agents in parallel for all selected comments
6. Works through each plan sequentially: code changes → tests → format → verify → commit
7. Posts an AI-labelled reply to the GitLab discussion thread after each commit
8. Resolves the discussion via the GitLab API

**Commit format:**
```
Address review comment from <reviewer>: <brief description>

- <change 1>
- <change 2>

Resolves comment #<id> on MR !<number>
```

## Installation

```bash
claude plugin install code-sentinel@eug-msv-claude-marketplace
```
