# code-sentinel

Expert code review and interactive GitLab MR comment resolution.

## Skills

### code-review

Trigger: "Review my feature branch", "PR review", "diff review"

Performs a senior engineer code review against the repo's actual default branch (auto-detected — `main`, `master`, or otherwise):

1. Fetches all remote branches, detects the default branch, and generates a diff via explicit merge-base
2. Determines repo mode (monorepo by default, or per-service) — asks the user when ambiguous
3. In per-service mode, uses git worktrees for full context on both branches; in monorepo mode, relies on the diff plus targeted `git show`/Read/Grep to avoid slow full checkouts
4. Identifies affected data flows with layer-by-layer ASCII diagrams (Web → Domain → Persistence → External)
5. Shows model/domain/DTO changes as a coloured diff tree (🔴 removed, 🟢 added, 🔵 changed, ⚪ unchanged)
6. Reviews each major change for logic, performance, security, SOLID violations, and test coverage
7. Produces a scored review (0–100) with copy-ready PR notes
8. Exports the full review to a markdown file in `.claude/code-review/`

**Rules:**
- Never posts to GitLab unless explicitly instructed
- Always compares against the auto-detected default branch (not hardcoded to `main`, not local)
- Skips worktree creation by default in monorepo mode; always uses worktrees in per-service mode
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
