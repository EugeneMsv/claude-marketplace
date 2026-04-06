---
name: msv-mr-nitpick-sentinel
description: Analyzes and helps address merge request comments interactively. Use when the user asks to "address MR comments", "review MR feedback", "handle reviewer comments", "respond to code review", or "fix review issues".
version: 0.1.0
---

# MR Nitpick Sentinel Skill

## Purpose

This skill helps developers efficiently address merge request review comments through an interactive workflow. It retrieves MR comments from GitLab using glab CLI, presents them in an organized format with code context, allows selection of which comments to address, generates an actionable implementation plan, and guides through fixing each issue with proper commit messages.

## When to Use

Invoke this skill when the user requests:
- "Address MR comments"
- "Review MR feedback"
- "Handle reviewer comments"
- "Respond to code review"
- "Fix review issues"
- "Work on review feedback"
- "Tackle reviewer nitpicks"

## Workflow

### Phase 1: Branch & MR Discovery

1. **Check Current Branch**
   - Run: `git branch --show-current`
   - Display branch name to user
   - Ask: "Is this the correct branch for the MR you want to address? If not, provide the branch name."

2. **Find Associated MR**
   - Run: `glab mr list --source-branch <branch-name>`
   - Extract MR number (format: !1234)
   - Display MR title and number
   - If no MR found, inform user and exit
   - If multiple MRs found, ask user to select one

### Phase 2: Comment Retrieval & Parsing

1. **Fetch Comments**
   - First, resolve the project path: `glab mr view <mr-number> --output json | python3 -c "import json,sys,urllib.parse; d=json.load(sys.stdin); print(urllib.parse.urlparse(d['web_url']).path.split('/-/')[0].lstrip('/'))"`
   - URL-encode the project path by replacing `/` with `%2F` (e.g., `org/group/repo` → `org%2Fgroup%2Frepo`)
   - Run: `glab api --paginate "projects/<url-encoded-project-path>/merge_requests/<mr-number>/discussions" > .claude/mr-<number>-comments.json`
   - Store output in `.claude/mr-<number>-comments.json`

2. **Parse JSON Structure**
   - The discussions API returns an array of discussion objects; flatten notes: `discussions[].notes[]`
   - Filter comments:
     - **Exclude**: `system: true` (auto-generated system comments)
     - **Focus on**: `resolvable: true` (discussion threads)
     - **Default**: `resolved: false` (unresolved comments)
     - User can request: "show-resolved" to include resolved comments

3. **Extract Comment Data**
   - For each comment, capture:
     - `id` - unique comment identifier
     - `type` - empty string for general, "DiffNote" for inline
     - `body` - comment text
     - `author.username` - reviewer username
     - `created_at` - timestamp
     - `resolved` - resolution status
     - For DiffNote type:
       - `position.new_path` - file path
       - `position.new_line` - line number

4. **Group Comments**
   - Separate into two groups:
     - **General comments**: no file/line association
     - **Inline comments**: tied to specific code location
   - Sort inline comments by file path, then line number

### Phase 3: Context Enrichment

For each inline comment (DiffNote type):

1. **Read Code Context**
   - Use Read tool: `Read(file_path, offset=line-3, limit=7)`
   - Shows 3 lines before, target line, 3 lines after

2. **Format Context**
   - Display with line numbers
   - Mark target line with `← Comment here`
   - Handle edge cases (file start/end)

### Phase 4: Display & User Interaction

1. **Display Formatted List**

   Present comments in this format:

   ```
   ═══════════════════════════════════════════════════════════
   MR REVIEW: !<number> - <title>
   Branch: <branch-name>
   ═══════════════════════════════════════════════════════════

   💬 Comment #1 - GENERAL - @<username> (<timestamp>)
   "<comment text>"
   Status: Unresolved

   ───────────────────────────────────────────────────────────

   📝 Comment #2 - INLINE - @<username> (<timestamp>)
   File: path/to/file.kt:45
   "<comment text>"

   Context:
     43: │     code line
     44: │     code line
     45: │     code line  ← Comment here
     46: │     code line
     47: │     code line

   Status: Unresolved

   ───────────────────────────────────────────────────────────
   ```

2. **Present Selection Options**

   Ask user:
   ```
   Which comments would you like to address?

   Options:
   - Enter comment numbers (comma-separated, e.g., "1,3,5")
   - "all" - address all unresolved comments
   - "show-resolved" - display resolved comments as well
   - "none" - cancel operation
   ```

3. **Parse User Selection**
   - Validate input format
   - Handle "all", "show-resolved", "none" keywords
   - Parse comma-separated numbers
   - Verify numbers exist
   - Build list of selected comments

### Phase 5: Plan Creation with Agents

**For Each Selected Comment:**

1. **Prepare Context Package**

   Gather information for the Plan agent:
   - Comment details: ID, author, text, timestamp
   - Code context: file path, line number, surrounding code (if inline)
   - MR information: number, title, branch
   - Relevant files identified from comment

2. **Launch Plan Agent**

   Use Task tool with `subagent_type=Plan`:
   ```
   Task(
     subagent_type="Plan",
     description="Plan for MR comment #<id>",
     prompt="""
     Create implementation plan to address this merge request review comment:

     MR: !<number> - <title>
     Comment #<id> from @<username>
     <File: path:line if inline>

     Comment: "<full comment text>"

     <Code context if inline>

     Analyze the comment and create a detailed implementation plan that:
     - Identifies the reviewer's concern
     - Determines necessary changes (code, tests, docs)
     - Lists specific files to modify
     - Provides step-by-step implementation steps
     - Specifies verification commands
     - Estimates effort (Low/Medium/High)

     Follow project coding standards and testing practices.
     """
   )
   ```

3. **Store Plan**

   The Plan agent will create: `.claude/mr-<number>-comment-<id>-plan.md`

   Plan file format:
   ```markdown
   # Plan: Address MR !<number> Comment #<id>

   ## Comment Context
   - **Author**: @<username>
   - **Date**: <timestamp>
   - **File**: <path:line> (if inline)
   - **Status**: Unresolved

   ## Comment
   "<full comment text>"

   ## Code Context
   ```
   <code snippet if inline>
   ```

   ## Analysis
   <Reviewer's concern and what needs to be addressed>

   ## Action Type
   <Test coverage / Bug fix / Refactor / Documentation / etc>

   ## Implementation Steps
   1. <specific action>
   2. <specific action>
   ...

   ## Files to Modify
   - `<file path>` - <what to change>
   - `<test file>` - <tests to add/update>

   ## Verification
   ```bash
   <commands to verify>
   ```

   ## Estimated Effort
   <Low / Medium / High>
   ```

4. **Launch All Plan Agents**

   - Run Plan agents in parallel for all selected comments
   - Wait for all agents to complete
   - Collect plan file paths

5. **Present Plans to User**

   Display summary:
   ```
   ═══════════════════════════════════════════════════════════
   PLANS CREATED FOR <N> COMMENTS
   ═══════════════════════════════════════════════════════════

   Comment #<id> from @<username>
   Plan: .claude/mr-<number>-comment-<id>-plan.md
   Effort: <Low/Medium/High>

   Comment #<id> from @<username>
   Plan: .claude/mr-<number>-comment-<id>-plan.md
   Effort: <Low/Medium/High>

   ═══════════════════════════════════════════════════════════
   ```

   Then inform user:
   ```
   Plans are ready. We'll work through them one by one.
   Starting with Comment #<id>...
   ```

### Phase 6: Sequential Pair Programming

**For Each Plan (in order):**

1. **Present Plan**

   - Read plan file: `.claude/mr-<number>-comment-<id>-plan.md`
   - Display plan to user
   - Ask: "Ready to work on this comment? (yes/skip/cancel)"

2. **Create Task List**

   Use TaskCreate to build task list from plan's implementation steps:
   - Each step becomes a task with description, activeForm
   - Mark first task as `in_progress`

3. **Execute Tasks**

   Follow standard iterative workflow:
   - Make code changes
   - Add/update tests during implementation
   - Format code (project formatter)
   - Run verification
   - Mark task completed
   - Get user confirmation
   - Move to next task

4. **Create Commit**

   After all tasks for the comment complete:
   ```bash
   git add <changed files>
   git commit -m "Address review comment from <reviewer>: <brief>

   - <change 1>
   - <change 2>
   - <change 3>

   Resolves comment #<id> on MR !<number>"
   ```

5. **Post Reply to Discussion**

   After the commit, post a concise AI-labelled reply to the GitLab discussion thread.
   Use the `discussion_id` from the parsed comments JSON (`discussions[].id`).

   ```bash
   glab api "projects/<encoded-path>/merge_requests/<mr-number>/discussions/<discussion_id>/notes" \
     --method POST \
     --field "body=*(AI-generated response)*

   <concise summary of what was changed and why>"
   ```

   - Start the body with `*(AI-generated response)*` on its own line
   - Follow with 1–3 sentences summarising the change
   - If multiple reviewer notes share the same discussion thread, post **one** reply covering all of them

6. **Resolve Discussion**

   After posting the reply, mark the discussion as resolved:

   ```bash
   glab api "projects/<encoded-path>/merge_requests/<mr-number>/discussions/<discussion_id>" \
     --method PUT \
     --field "resolved=true"
   ```

   Confirm resolution by checking `resolved: true` in the response. If the API returns an
   error or `resolved` is still false, report the failure to the user but continue.

7. **Confirm Progress**

   - Display commit result
   - Show verification output
   - Ask: "Comment #<id> addressed. Continue to next? (yes/no)"

8. **Repeat for Next Comment**

9. **Final Summary**

   After all comments addressed:
   ```
   ═══════════════════════════════════════════════════════════
   ALL COMMENTS ADDRESSED
   ═══════════════════════════════════════════════════════════

   Summary:
   - <N> commits created
   - <N> GitLab discussions resolved
   - All tests passing

   Plan files stored in .claude/ for reference.

   You can now push changes and notify reviewers.
   ═══════════════════════════════════════════════════════════
   ```

## Rules

### MUST

- Use `glab api --paginate "projects/<encoded-path>/merge_requests/<number>/discussions"` for comment retrieval — never use `glab mr view --comments` as it silently truncates at 20 results
- Filter out system comments (`system: true`)
- Show file/line context for all inline comments using Read tool
- Store all temporary files in `.claude/` directory
- Launch Plan agent for each selected comment using Task tool
- Run all Plan agents in parallel when possible
- Store each plan as `.claude/mr-<number>-comment-<id>-plan.md`
- Wait for all Plan agents to complete before proceeding
- Present plan summary to user before starting implementation
- Work through comments sequentially (one at a time)
- Create TaskList for each comment's implementation steps
- Format code according to project standards before verification
- Run tests to verify each change
- One commit per comment addressed
- Use specified commit message format
- Display commit result and verification output to user
- Post an AI-labelled reply to the GitLab discussion after each commit, starting with `*(AI-generated response)*`
- Resolve the GitLab discussion via PUT after posting the reply
- Keep plan files in `.claude/` for reference

### SHOULD

- Default to unresolved comments only
- Group comments by type (general vs inline)
- Sort inline comments by file path, then line number
- Present comments with clear visual separation
- Launch Plan agents with comprehensive context (comment, code, files)
- Allow user to skip or cancel at each comment
- Estimate effort in each plan (Low/Medium/High)
- Handle edge cases gracefully (empty comments, file not found, etc.)
- Provide helpful error messages
- Track progress across multiple comments

### DO NOT

- Make any code changes without explicit user approval
- Include system-generated comments in display
- Skip code context for inline comments
- Skip launching Plan agent for any selected comment
- Start implementation before all plans are created
- Work on multiple comments simultaneously
- Create generic commit messages
- Skip test verification
- Combine multiple comment fixes in one commit
- Proceed if tests fail
- Delete plan files after completion (keep for reference)

### COMMIT PATTERN

```
Address review comment from <reviewer>: <brief description>

- <specific change 1>
- <specific change 2>
- <specific change 3>

Resolves comment #<comment-id> on MR !<mr-number>
```

**Pattern Rules:**
- First line: "Address review comment from" + reviewer username + brief description
- Body: Bulleted list of specific changes made
- Footer: Reference to comment ID and MR number
- Keep first line under 72 characters
- Use active voice for changes ("Add", "Update", "Fix", "Remove")
