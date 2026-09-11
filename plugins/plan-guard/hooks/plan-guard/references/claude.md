Planning requirements for this session.

STEP 0 — CLASSIFY THE PLAN (do this first): decide whether this is an IMPLEMENTATION plan (produces and applies code changes) or a DISCOVERY plan (research, investigation, analysis, design — no code changes), and STATE the classification at the top of the plan.
- If DISCOVERY: only MANDATE 0 and MANDATE 6 are binding; mark the build/test/commit/ verification mandates N/A.
- If IMPLEMENTATION: ALL mandates below are binding.

MANDATE 0 — TABLE OF CONTENTS. The plan MUST begin with a table of contents listing every task.

MANDATE 1 — GIT PREP (optional, ASK). The FIRST task MUST be optional git prep: stash unchanged work, switch to master/main, pull latest, then create a feature branch. You MUST ASK during planning whether this task is needed and include/omit it per the answer. If a Jira ticket is in context, SHALL suggest the branch name from it (e.g. TASK-123-short-description); otherwise ask.

MANDATE 2 — VERIFICATION REQUIRED + EXACT COMMANDS. Every task that PRODUCES OR CHANGES CODE MUST include a verification step proving the change works (unit test, build, or runnable check); such a task is NOT complete without one. Other tasks SHOULD include verification wherever a meaningful check exists. Every verification MUST use exact, directly-runnable CLI commands scoped to that task — never a vague phrase.
  ❌ "build + test"
  ✅ bazel test //path/to:FooTest
  ✅ gradle :module:test --tests '*.FooTest'

MANDATE 3 — TEST-CREATING TASKS. Any task that creates tests MUST carry this rule embedded in the task itself.
  3a. DURING PLANNING: each such task gets exactly ONE ordered subtask (created now via TaskCreate), sequenced AFTER the task's implementation subtasks, whose sole job is to identify and confirm the test use cases/scenarios.
  3b. The plan MUST NOT enumerate the actual use cases or the per-case implementation subtasks.
  3c. AT EXECUTION TIME: this subtask is started ONLY after the task's implementation work is finished. It first presents the scenarios for the user's confirmation, then creates ordered subtasks one per case (simplest → most comprehensive) and implements them strictly one at a time — each written and verified before the next — NEVER in bulk.

MANDATE 4 — COMMIT PER TASK. Every task THAT CHANGES FILES MUST end with a git commit formatted "Task N: <description>". A task that changes no files (e.g. pure discovery/identification) requires no commit.

MANDATE 5 — VERIFICATION DISCOVERY. The SECOND-TO-LAST task MUST exhaustively discover every LOCAL verification in this project's SDLC (NOT CI pipeline files): scan code, build files, local scripts, and existing memory for ALL local phases (unit, integration, e2e/UAT, smoke, contract, lint, etc.). Finding one type does NOT end the search.
  5a. Each type FOUND MUST become its OWN ordered subtask created DURING PLANNING, naming its exact command, in order:  lint → unit → integration → e2e/smoke, etc.
  5b. Each type NOT found MUST be stated explicitly (e.g. "integration tests: not found, nothing to run") — never silently skipped.

MANDATE 6 — DOCUMENTATION. Relevant docs MUST be IDENTIFIED during planning (specific files/pages, e.g. README.md, CLAUDE.md, a Confluence page); the LAST task MUST explicitly NAME which of those documents to update for this change — not a generic "update documentation".

COMPLIANCE GATE (MUST be the last thing in the plan). The plan is INVALID unless it ENDS with a "Compliance Checklist" that lists each applicable mandate (0–6) and, on one line each, the concrete evidence it is satisfied — task number, literal command, branch name, or doc name — or marks it N/A with a reason. The evidence MUST be concrete, not a restatement of the mandate. If any box cannot be ticked, fix the plan before presenting it.
