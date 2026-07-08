---
name: msv-code-review
description: |
  This skill should be used when the user asks to "review my branch",
  "review this MR", "PR review", "diff review", or mentions reviewing
  changes, analyzing commits, or comparing branches. Supports both
  monorepo (default) and per-service repos — asks which mode applies
  when ambiguous. Auto-detects the actual default branch (main or
  master) instead of assuming main. In monorepo mode, diffs via
  explicit merge-base to avoid noise from unrelated commits landed on
  the default branch since the feature branch was cut; per-service
  mode keeps the original triple-dot diff.
---

# Code Reviewer Skill

## Trigger
- User requests code review, PR review, or diff review
- User mentions reviewing changes, analyzing commits, or comparing branches

## Instructions

You are an expert Senior Software Engineer performing a code review.

### Workflow

1. **Get Branch Information**
    - Ask user for branch name if not provided
    - Use `git fetch --all` to update all remote branches

2. **Determine Repository Mode**
    - Two modes: **monorepo** (default) and **per-service** (a repo dedicated to a single service/app)
    - Infer mode from context where possible (repo name/path conventions, many unrelated top-level service dirs, explicit user statement)
    - If ambiguous, **ASK the user** which mode applies before proceeding
    - If unspecified after asking, **default to monorepo mode**
    - Affects worktree usage in step 5 (Analyze Changes) only — does NOT affect diff generation, default-branch detection, or any other step

3. **Check for GitLab MR Context** (if applicable)
    - Use `glab mr list --source-branch <branch-name>` to find associated MR
    - If MR exists, use `glab mr view <mr-number> --comments` to retrieve all comments
    - Analyze MR comments to identify:
        - **Reviewer Requests**: What changes/fixes were requested
        - **Author Responses**: How author addressed each request
        - **Unresolved Discussions**: Any open threads or concerns
        - **Historical Context**: Previous iterations and decisions
    - Use this context to inform the review (do NOT store separately)

4. **Generate Diff**
    - Detect the actual default branch in BOTH modes (do NOT assume `main`):
      ```bash
      DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")
      ```
    - **Monorepo mode** (explicit merge-base — isolates the diff from unrelated commits that landed on the default branch after the feature branch was cut, which is common in large monorepos):
      - Compute the merge-base and log the resulting SHA:
        ```bash
        git merge-base origin/<default-branch> origin/<branch>
        ```
      - Diff from that merge-base to the branch tip (explicit two-step form, not a bare triple-dot shorthand — keeps the merge-base SHA visible as its own auditable step):
        ```bash
        git diff <merge-base-sha>..origin/<branch> > .claude/code-review/diff-<branch>-<default-branch>.txt
        ```
    - **Per-service mode** (original triple-dot approach — sufficient for a single-service repo where default-branch churn is low):
      ```bash
      git diff origin/<default-branch>...origin/<branch> > .claude/code-review/diff-<branch>-<default-branch>.txt
      ```
    - If diff is empty, verify branch exists and has changes

5. **Analyze Changes**
    - Read the diff file thoroughly
    - In **per-service mode**, use git worktree for the default branch and another one for the target branch (see 5.1)
    - In **monorepo mode**, skip worktree creation by default; rely on the diff file plus targeted `git show <sha>:<path>`, Read, and Grep against the current working tree (see 5.1)
    - Identify major changes (exclude tests, minor refactors, comments)
    - Focus on: new logic, architectural changes, significant dependency changes
    - Always MUST identify the data flows which are affected by the changes
    - Always MUST identify Model/domain/POJO/DTO changes

5.1 **Git worktree (mode-conditional)**
- **Per-service mode**: Always create a worktree per branch (default branch + target branch) — cheap for a single-service repo, gives full context for:
    - The whole picture of the affected files in the diff
    - The flows comparison/changes (see 5.2)
    - Any other details not in the diff but useful for the human reviewer
- **Monorepo mode**: Do NOT create worktrees by default — checking out 100k+ files is slow for little marginal value. Instead:
    - `git show <merge-base-sha>:<path>` / `git show origin/<branch>:<path>` to read specific file versions without a full checkout
    - Read and Grep against the current working tree for surrounding context
    - Only fall back to a worktree if the user explicitly asks, or targeted `git show`/Read/Grep genuinely can't answer a question needing broader repo-wide context

5.2 **Identifying the affected flows** and 5.3 **Model/domain/POJO/DTO changes approach**

Load `references/flow-diagram-examples.md` for the full checklist and worked ASCII examples for
both sub-steps before producing flow diagrams or model diff trees.

6. **Prioritize by Impact**
    - Reorder from most to least impactful:
        - Core functionality changes (highest priority)
        - API/interface modifications
        - Architectural changes
        - Algorithm updates
        - Configuration changes (lowest priority)

7. **Review Each Major Change**

   For each prioritized change, analyze:

    - **Logic**: Bugs, edge cases, incorrect assumptions
    - **Performance**: O(n) complexity, database queries (N+1), memory usage
    - **Security**: Input validation, SQL injection, XSS, auth issues
    - **Standards**: Deviation from Java codestyle (final, var, records)
    - **SOLID Principles**: SRP, OCP, LSP, ISP, DIP violations
    - **Maintainability**: Clarity, naming, documentation

8. **Test Coverage**
    - Check if changes are covered by tests
    - Suggest test cases for untested changes
    - Verify test structure follows Given-When-Then

9. **Provide Review Summary**

   Load `references/review-summary-template.md` for the exact output format and fill it in with
   this review's findings.

10. **Export final review to markdown**

### Rules

- MUST use `git --no-pager` for clean output
- MUST auto-detect the default branch via `git symbolic-ref refs/remotes/origin/HEAD` (fallback to `main`) — NEVER hardcode `origin/main`
- In **monorepo mode**, MUST compute the diff via explicit merge-base (`git merge-base origin/<default-branch> origin/<branch>`, then `git diff <merge-base-sha>..origin/<branch>`) — NEVER a bare triple-dot shorthand
- In **per-service mode**, use the original triple-dot diff (`git diff origin/<default-branch>...origin/<branch>`)
- MUST store diff and review artifacts under `.claude/code-review/` (not flat in `.claude/`)
- MUST ask the user for mode (monorepo vs. per-service) when it cannot be confidently inferred, defaulting to monorepo if still unspecified
- MUST skip git worktree creation by default in monorepo mode — use the diff file plus targeted `git show`/Read/Grep instead
- MUST use git worktree per branch by default in per-service mode
- MUST use `mcp__sequentialthinking__sequentialthinking` for complex analysis
- MUST reference specific file paths with line numbers
- MUST include code snippets for top 3 most significant changes
- MUST verify test coverage for all major changes
- MUST present the review output in chat — NEVER post to GitLab MR unless user explicitly instructs it
- MUST draw ASCII before/after directory layout diagrams when packages, modules, or files are reorganized
- DO NOT review test files in detail (only verify coverage)
- DO NOT comment on formatting if spotlessApply will handle it
- DO NOT mention files where only imports changed — skip them entirely

### Example Invocation

User: "Review my feature branch feature/user-authentication"

## Additional Resources

### Reference Files

- **`references/flow-diagram-examples.md`** - Full checklist and worked ASCII examples for identifying affected flows (5.2) and model/DTO diff trees (5.3)
- **`references/review-summary-template.md`** - Exact output format for the final review summary (step 9)
