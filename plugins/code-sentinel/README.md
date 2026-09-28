# code-sentinel

Expert code review and interactive GitLab MR comment resolution.

## Skills

### code-review

Trigger: "Review my feature branch", "PR review", "diff review"

Performs a senior engineer code review against the repo's actual default branch (auto-detected — `main`, `master`, or otherwise):

1. Fetches remote branches, determines repo mode (monorepo by default, or per-service), detects the default branch, and reads merge request context
2. Requires ticket, linked epic, and architecture research before generating the diff; missing access is a visible blocker unless the user explicitly authorizes proceeding with that gap. An independent reviewer then rewrites the resulting problem statement until a newcomer could restate it in one sentence
3. Generates a diff via explicit merge-base. In per-service mode, uses git worktrees for full context on both branches; in monorepo mode, relies on the diff plus targeted `git show`/Read/Grep to avoid slow full checkouts
4. Identifies affected data flows with layer-by-layer ASCII diagrams (Web → Domain → Persistence → External)
5. Shows model/domain/DTO changes as a coloured diff tree (🔴 removed, 🟢 added, 🔵 changed, ⚪ unchanged)
6. Reviews each major change for logic, performance, security, SOLID violations, and test coverage
7. Opens the review with Key Docs and two onboarding paragraphs, then MR context, one global reading order, flows and model changes, and the change analysis; includes a score (0–100) and copy-ready PR notes
8. Exports the full review to a markdown file in the selected runtime’s artifact directory

**Rules:**
- Never silently skips ticket and architecture context; distinguish unavailable sources from completed searches with no results
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
5. Plans each selected comment, delegating only when supported and authorized
6. Works through each plan sequentially: code changes → tests → format → verify → commit
7. Posts an AI-labelled reply when explicitly authorized
8. Resolves the discussion when authorized

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

## Codex support

Both manifests share the same skills. Each skill loads only its host-specific reference under `references/codex.md` or `references/claude.md`. The code-review criteria remain shared. Codex artifacts use `.Codex/<skill>/`; Claude artifacts use `.claude/<skill>/`, subject to project instructions.
