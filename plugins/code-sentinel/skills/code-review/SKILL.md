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
## Runtime integration

Use the current host to select exactly one reference: [Codex](references/codex.md) or [Claude Code](references/claude.md). Read it before starting. It defines artifact paths, planning, and tool access; the review criteria below are shared. Follow explicit user authorization and repository instructions.


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
    - If MR exists, use `glab mr view <mr-number> --comments` to retrieve the description and all comments
    - Analyze the **MR description** (not just comments) to identify:
        - **Stated Scope**: What the author says changed — cross-check against the actual diff to catch undisclosed/unscoped changes
        - **Design Rationale**: Why an approach was taken, including any self-disclosed tradeoffs (e.g. "temporary" workarounds) — these lower the severity of a related review finding since they're already known and intentional
        - **Verification Evidence**: Any manual/automated test steps or validation the author already ran — note precisely what it does and does NOT cover
    - Analyze MR comments to identify:
        - **Reviewer Requests**: What changes/fixes were requested
        - **Author Responses**: How author addressed each request
        - **Unresolved Discussions**: Any open threads or concerns
        - **Historical Context**: Previous iterations and decisions
    - Use this context to inform the review (do NOT store separately)
    - Flag as a finding when a real, non-trivial change in the diff is absent from the MR description's stated scope — even if a reviewer comment confirms it's intentional, it should still be documented in the description for future readers

3.5 **Deep Research Context** (Required — complete before generating the diff)
    - Purpose: ground the review in the ticket's intent and any existing architecture docs before judging the diff
    - Extract a Jira key from the MR title/description or branch name (e.g. `PROJ-12345` pattern). If none is found, ask for the ticket or confirmation that the change has no ticket; do NOT invent one or silently skip context research. For a confirmed ticketless change, research the relevant architecture and mark ticket/epic context not applicable.
    - Delegate to an available research agent when delegation is supported and authorized; otherwise use an available general-purpose agent or perform the research inline. The researcher must check its actual tool access; missing tools in the parent alone do not establish that delegated access is unavailable.
    - The researcher must:
        - Fetch the Jira ticket for scope/acceptance criteria
        - Inspect the fetched ticket for a parent epic and fetch it when linked; only say "no epic linked" after checking the ticket
        - Search Confluence for relevant architecture docs — use the user's search terms/spaces when supplied; otherwise make 2-3 Rovo-style calls varying phrasing/keywords, merge results, and rank their intersection first. Fetch the top 2-3 relevant pages before drawing conclusions. Record source links and last-modified dates, flag pages older than one year as potentially stale, and treat code as ground truth over docs.
        - Identify the nearest thing a reader could confuse with the change (a sibling app/channel/service, a same-named system, an overlapping ticket) and verify the change's boundary against it with data or code, not docs alone
        - Return a **Key Docs** line, then the two blocks below, written for a reviewer new to the area. Key Docs: the Jira ticket link + last-modified date · the epic link + last-modified date, or "no epic linked" (only after checking the ticket) · each fetched Confluence page title + link + last-modified date, ⚠️ on pages older than one year · "not applicable" for a user-confirmed ticketless change
    - **What the MR does** block. Each label below appears **exactly once**, in this order. Put multi-point content in nested sub-bullets under its label; never repeat a label (no second **Problem:** or third **The fix:** bullet).
        - **Problem:** the centerpiece and the most developed part of the block. Open with one plain-language sentence a newcomer could repeat back, then tell one causal story in nested bullets, covering these beats in order:
            1. **Purpose:** what the affected mechanism is for, in user or business terms
            2. **How it decides:** the concrete identifiers, rules, or data it keys on
            3. **What goes wrong:** one concrete scenario, specific inputs → the wrong outcome the system produces
            4. **Consequence:** who or what is harmed (users, revenue, privacy, reliability) and how badly
            5. **Live or latent:** whether it happens today (with the data and date checked) or only after a future step (name that step)
            6. **Evidence:** which beats are verified in code or data, which are author claims, which are inferred
          A fact that does not advance this story belongs in another label, in How it relates to <X>, or nowhere. A list of true facts that the reader must assemble into a problem is not a problem statement.
        - **Why not the obvious fix:** name the obvious fix, then the constraint that rules it out, with its source (code or doc)
        - **The fix:** what the change does in behavioural terms (inputs → what the system now returns or does), tied back to the "What goes wrong" scenario
        - **Side effects:** behaviour the change alters beyond the stated problem, such as a rule applied more widely than the problem needs or a shared parser change. Omit the label when there are none.
        - **Why here:** why this system/layer is the right place (e.g. clients already shipped, only the server can stop it). When an epic is linked, add what it aims to achieve here.
    - **How it relates to <X>** block, where X is the nearest confusable entity found above: state what the change does and does NOT touch, with the evidence checked
    - Style for both blocks: plain language, expand jargon on first use, one causal step per nested bullet, no file:line refs. Mark inference and unknowns inline ("I infer", "not verified", "checked one day only") instead of in a separate trust table. Distinguish verified source content, author claims, and code-derived inferences.
    - If required ticket/epic retrieval or architecture search cannot run because access is unavailable, report the blocker and what is needed to resolve it before step 4. Resume after access is restored, the user supplies the missing source content, or the user explicitly authorizes a review with that gap. Do not equate unavailable access with "no epic linked" or "no relevant docs found."
    - A completed search with no relevant architecture docs is a valid result: state what was searched and that none were found, then use clearly labeled code-derived architecture context. Do not fabricate sources to fill the template.
    - Use the research to inform Design Rationale and scope judgments and open the review summary (step 9) with **Ticket & Architecture Context** in chat and in any exported review. Include the Key Docs line, the What the MR does and How it relates to <X> blocks, and any gaps or explicit user-authorized exception. Never replace this section with only a findings summary or a file link; the research also does not replace reading the actual diff.

3.6 **Problem Statement Review** (Required — complete before generating the diff)
    - Give the researcher's What the MR does and How it relates to <X> blocks, plus the sources they cite, to an independent reviewer: a different agent from the researcher when delegation is supported and authorized, otherwise a separate inline pass of your own
    - The reviewer rewrites the blocks until they meet step 3.5. It passes them only when:
        - a newcomer could repeat the problem in one sentence that names the input, the wrong outcome, and who is harmed
        - every Problem beat is present and the beats read as one connected chain, each following from the one before
        - each label appears once
    - The reviewer may rephrase, reorder, and cut, but adds no fact absent from the cited sources. A beat it cannot fill stays in, marked unknown, with what would settle it.
    - Use the reviewed blocks in the review output

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
        git diff <merge-base-sha>..origin/<branch> > <artifact-dir>/diff-<branch>-<default-branch>.txt
        ```
    - **Per-service mode** (original triple-dot approach — sufficient for a single-service repo where default-branch churn is low):
      ```bash
      git diff origin/<default-branch>...origin/<branch> > <artifact-dir>/diff-<branch>-<default-branch>.txt
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

6. **Set the Review Order**
    - Reorder from most to least impactful:
        - Core functionality changes (highest priority)
        - API/interface modifications
        - Architectural changes
        - Algorithm updates
        - Configuration changes (lowest priority)
    - Present exactly one **Reading Order** for the entire review: a numbered sequence of
      concrete files/classes/methods, with a short explanation of what to understand at each stop.
      Choose one traversal that connects all affected flows and shared models; include shared
      components once. Do not offer alternative top-down/bottom-up routes or repeat reading
      orders under individual changes or flows.
    - After ticket/architecture and MR context, use this presentation order in chat and any
      exported review: **Reading Order → Flows and model changes → Changes**. Put the flow
      diagrams and model diff trees from steps 5.2/5.3 immediately after the global reading
      order, before the prioritized change list and detailed analysis. Impact ranking governs
      the change analysis; the reading order guides the reader through the code.

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
- MUST store diff and review artifacts under `<artifact-dir>/` (not in the artifact root)
- MUST ask the user for mode (monorepo vs. per-service) when it cannot be confidently inferred, defaulting to monorepo if still unspecified
- MUST complete Deep Research Context (step 3.5) and Problem Statement Review (step 3.6) before generating the diff, and include the reviewed context section in the review output; handle blockers and explicit user-authorized exceptions as defined there. Never skip either silently.
- Confluence search strategy for step 3.5 is out of scope of this skill — if the user hasn't given search terms, default to a Rovo-style search (2-3 calls with varied phrasing/keywords) with a recency check on results
- MUST skip git worktree creation by default in monorepo mode — use the diff file plus targeted `git show`/Read/Grep instead
- MUST use git worktree per branch by default in per-service mode
- Use sequential-thinking MCP for complex analysis when available
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
