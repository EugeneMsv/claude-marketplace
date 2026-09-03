#!/usr/bin/env python3
"""UserPromptSubmit/PreToolUse hook — injects planning requirements into plan mode.

Two modes:
- AI (default): scans project context and generates tailored requirements via the API.
- Static (set PLAN_GUARD_STATIC_RULES): injects fixed rules only — no context, no API call.
"""

import json
import os
import sys
from pathlib import Path

from anthropic_client import AnthropicClient

BUILD_FILE_HINTS = {
    "build.gradle": "Gradle (Java/Kotlin)",
    "build.gradle.kts": "Gradle Kotlin DSL",
    "pom.xml": "Maven",
    "package.json": "Node.js/npm",
    "requirements.txt": "Python/pip",
    "pyproject.toml": "Python/pyproject",
    "go.mod": "Go modules",
    "Makefile": "Make",
    "Cargo.toml": "Rust/Cargo",
    "MODULE.bazel": "Bazel",
    "WORKSPACE.bazel": "Bazel",
    "WORKSPACE": "Bazel",
    "BUILD.bazel": "Bazel",
}

PROMPT_TEMPLATE = """\
You are a planning assistant for a software engineer. Based on the project context below, \
produce a set of planning directives. Your output is NOT read by a human — it is injected \
VERBATIM as binding system directives into a separate planning LLM that is entering plan mode. \
Optimize for machine compliance, not human readability. Output the directives the planning agent \
must follow — the rules a plan has to satisfy — never the actual commands, branch names, or the \
plan itself; state only what must be true, not the answers.

Format the output as numbered "MANDATE N:" headers using MUST/SHALL imperatives (not loose \
prose bullets), break any multi-part rule into lettered atomic sub-points (3a, 3b, ...), and \
END the output with the COMPLIANCE GATE described below. Your output MUST mirror this canonical \
structure exactly (STEP 0 → MANDATE 0..6 → COMPLIANCE GATE) so it is shape-identical to the \
project's static rule set.

The output MUST contain, in this exact order:

STEP 0 — CLASSIFY THE PLAN (must come first): instruct the agent to decide whether this is an \
IMPLEMENTATION plan (produces and applies code changes) or a DISCOVERY plan (research, \
investigation, analysis, design — no code changes) and to STATE the classification at the top of \
the plan. If DISCOVERY: only MANDATE 0 and MANDATE 6 are binding; all build/test/commit/ \
verification mandates are N/A. If IMPLEMENTATION: ALL mandates are binding.

MANDATE 0: the plan MUST begin with a table of contents listing every task.

MANDATE 1: the FIRST task is optional git prep — stash unchanged work, switch to master/main, \
pull latest, then create a feature branch. "Optional" means the agent MUST ASK during planning \
whether this task is needed and include/omit it per the answer. SHALL auto-suggest the branch \
name from a Jira ticket if one is in context (e.g. TASK-123-logger-improvement, where TASK-123 \
is the ticket), otherwise ask for it.

MANDATE 2: every task that PRODUCES OR CHANGES CODE MUST include a verification step proving the \
change works (unit test, build, or runnable check) — such a task is NOT complete without one; \
other tasks SHOULD include verification wherever a meaningful check exists. Every verification \
MUST use exact, directly-runnable CLI commands scoped to that task — never a vague phrase. \
Include a concrete contrast built from THIS project's real build tool, e.g. ❌ "build + test" \
vs ✅ `<literal command from context, like bazel test //path:FooTest>`.

MANDATE 3: any task that CREATES TESTS MUST carry this rule embedded in the task itself.
  3a. DURING PLANNING: each such task gets exactly ONE ordered subtask (created now via \
TaskCreate), sequenced AFTER the task's implementation subtasks, whose sole job is to identify \
and confirm the test use cases/scenarios.
  3b. The plan MUST NOT enumerate the actual use cases or the per-case implementation subtasks.
  3c. AT EXECUTION TIME: this subtask is started ONLY after the task's implementation work is \
finished. It first presents the scenarios for the user's confirmation, then creates ordered \
subtasks one per case (simplest → most comprehensive) and implements them strictly one at a \
time — each written and verified before the next — NEVER in bulk.

MANDATE 4: every task THAT CHANGES FILES MUST end with a git commit formatted "Task N: \
<description>"; a task that changes no files (e.g. pure discovery/identification) requires no commit.

MANDATE 5: the SECOND-TO-LAST task MUST exhaustively discover every LOCAL verification in this \
project's SDLC (NOT CI pipeline files) — scan code, build files, local scripts, and existing \
memory for ALL local phases (unit, integration, e2e/UAT, smoke, contract, lint, etc.). Finding \
one type does NOT end the search.
  5a. Each type FOUND MUST become its OWN ordered subtask created DURING PLANNING, naming its \
exact command, in order: unit → integration → e2e/smoke → lint, etc.
  5b. Each type NOT found MUST be stated explicitly (e.g. "integration tests: not found, nothing \
to run") — never silently skipped.

MANDATE 6: relevant documentation MUST be IDENTIFIED during planning (specific files/pages, e.g. \
README.md, CLAUDE.md, a Confluence page); the LAST task MUST explicitly NAME which of those \
documents to update for this change — not a generic "update documentation".

COMPLIANCE GATE (MUST be the final section of the output): instruct that the plan is INVALID \
unless it ENDS with a "Compliance Checklist" that lists each applicable mandate (0–6) and, on \
one line each, the concrete evidence it is satisfied — task number, literal command, branch \
name, or doc name — or marks it N/A with a reason. The evidence MUST be concrete, not a \
restatement of the mandate. If any box cannot be ticked, the agent fixes the plan before \
presenting it.

Be specific — use the actual commands from the project context. If you cannot determine the \
exact command, use a sensible default for the detected build tool. Output ONLY the directives \
(STEP 0 through the COMPLIANCE GATE), no preamble.

PROJECT CONTEXT:
{context}
"""

STATIC_RULES = """\
Planning requirements for this session.

STEP 0 — CLASSIFY THE PLAN (do this first): decide whether this is an IMPLEMENTATION plan \
(produces and applies code changes) or a DISCOVERY plan (research, investigation, analysis, \
design — no code changes), and STATE the classification at the top of the plan.
- If DISCOVERY: only MANDATE 0 and MANDATE 6 are binding; mark the build/test/commit/ \
verification mandates N/A.
- If IMPLEMENTATION: ALL mandates below are binding.

MANDATE 0 — TABLE OF CONTENTS. The plan MUST begin with a table of contents listing every task.

MANDATE 1 — GIT PREP (optional, ASK). The FIRST task MUST be optional git prep: stash unchanged \
work, switch to master/main, pull latest, then create a feature branch. You MUST ASK during \
planning whether this task is needed and include/omit it per the answer. If a Jira ticket is in \
context, SHALL suggest the branch name from it (e.g. TASK-123-short-description); otherwise ask.

MANDATE 2 — VERIFICATION REQUIRED + EXACT COMMANDS. Every task that PRODUCES OR CHANGES CODE \
MUST include a verification step proving the change works (unit test, build, or runnable check); \
such a task is NOT complete without one. Other tasks SHOULD include verification wherever a \
meaningful check exists. Every verification MUST use exact, directly-runnable CLI commands scoped \
to that task — never a vague phrase.
  ❌ "build + test"
  ✅ bazel test //path/to:FooTest
  ✅ gradle :module:test --tests '*.FooTest'

MANDATE 3 — TEST-CREATING TASKS. Any task that creates tests MUST carry this rule embedded in \
the task itself.
  3a. DURING PLANNING: each such task gets exactly ONE ordered subtask (created now via \
TaskCreate), sequenced AFTER the task's implementation subtasks, whose sole job is to identify \
and confirm the test use cases/scenarios.
  3b. The plan MUST NOT enumerate the actual use cases or the per-case implementation subtasks.
  3c. AT EXECUTION TIME: this subtask is started ONLY after the task's implementation work is \
finished. It first presents the scenarios for the user's confirmation, then creates ordered \
subtasks one per case (simplest → most comprehensive) and implements them strictly one at a \
time — each written and verified before the next — NEVER in bulk.

MANDATE 4 — COMMIT PER TASK. Every task THAT CHANGES FILES MUST end with a git commit formatted \
"Task N: <description>". A task that changes no files (e.g. pure discovery/identification) \
requires no commit.

MANDATE 5 — VERIFICATION DISCOVERY. The SECOND-TO-LAST task MUST exhaustively discover every \
LOCAL verification in this project's SDLC (NOT CI pipeline files): scan code, build files, local \
scripts, and existing memory for ALL local phases (unit, integration, e2e/UAT, smoke, contract, \
lint, etc.). Finding one type does NOT end the search.
  5a. Each type FOUND MUST become its OWN ordered subtask created DURING PLANNING, naming its \
exact command, in order:  lint → unit → integration → e2e/smoke, etc.
  5b. Each type NOT found MUST be stated explicitly (e.g. "integration tests: not found, nothing \
to run") — never silently skipped.

MANDATE 6 — DOCUMENTATION. Relevant docs MUST be IDENTIFIED during planning (specific \
files/pages, e.g. README.md, CLAUDE.md, a Confluence page); the LAST task MUST explicitly NAME \
which of those documents to update for this change — not a generic "update documentation".

COMPLIANCE GATE (MUST be the last thing in the plan). The plan is INVALID unless it ENDS with a \
"Compliance Checklist" that lists each applicable mandate (0–6) and, on one line each, the \
concrete evidence it is satisfied — task number, literal command, branch name, or doc name — or \
marks it N/A with a reason. The evidence MUST be concrete, not a restatement of the mandate. If \
any box cannot be ticked, fix the plan before presenting it.
"""


def collect_context(cwd: str) -> tuple[str, list[str]]:
    """Return (context_for_model, discoveries) where discoveries are short human-readable
    notes on what was found, used to summarize the status line."""
    base = Path(cwd)
    parts = []
    discoveries = []

    # Detected build tools (deduped — several markers can map to one tool, e.g. Bazel)
    found_tools = list(
        dict.fromkeys(
            label for fname, label in BUILD_FILE_HINTS.items() if (base / fname).exists()
        )
    )
    if found_tools:
        parts.append(f"Build tools: {', '.join(found_tools)}")
        discoveries.append(f"build tooling ({', '.join(found_tools)})")

    # CLAUDE.md or .claude/CLAUDE.md — first 60 lines
    for candidate in [base / "CLAUDE.md", base / ".claude" / "CLAUDE.md"]:
        if candidate.exists():
            try:
                lines = candidate.read_text(errors="ignore").splitlines()[:60]
                parts.append("CLAUDE.md:\n" + "\n".join(lines))
                discoveries.append(f"project instructions ({candidate.name})")
            except OSError:
                pass
            break

    # key-commands.md
    for candidate in [
        base / ".claude" / "rules" / "key-commands.md",
        Path.home() / ".claude" / "rules" / "key-commands.md",
    ]:
        if candidate.exists():
            try:
                parts.append(f"key-commands.md:\n{candidate.read_text(errors='ignore')[:600]}")
                discoveries.append("key build/test commands")
            except OSError:
                pass
            break

    return "\n\n".join(parts)[:1200], discoveries


def build_requirements_message(client: AnthropicClient, context: str) -> str:
    """Generate the planning requirements via a cheap classification-tier model."""
    # ANTHROPIC_MODEL is a CLI alias ("opus"), not a real model id — resolve a concrete one.
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    return client.complete(
        model=model,
        prompt=PROMPT_TEMPLATE.format(context=context),
        max_tokens=2000,
        # "cheap classification-tier" per the docstring above - medium matches
        # that intent instead of silently inheriting the API's "high" default.
        effort="medium",
    )


def emit(hook_event: str, system_message: str, status_line: str) -> None:
    """Print the hook response that injects `system_message` into plan-mode context."""
    print(json.dumps({
        "systemMessage": status_line,
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": system_message,
        },
    }))


def static_mode_enabled() -> bool:
    """When set, inject fixed rules only — no context scan, no Anthropic call."""
    return os.environ.get("PLAN_GUARD_STATIC_RULES", "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    hook_input = json.load(sys.stdin)
    hook_event = hook_input.get("hook_event_name", "PreToolUse")
    cwd = hook_input.get("cwd", os.getcwd())

    # For UserPromptSubmit, only activate when actually in plan mode
    if hook_event == "UserPromptSubmit" and hook_input.get("permission_mode") != "plan":
        print("{}")
        return

    # Static mode: inject the fixed rules verbatim, skipping context + model entirely
    if static_mode_enabled():
        emit(hook_event, STATIC_RULES,
             "[plan-enforcer] 📋 Static planning rules injected (AI generation off).")
        return

    if not AnthropicClient.has_credentials():
        print(json.dumps({"systemMessage": "[plan-enforcer] No credentials detected, skipping"}))
        return

    try:
        context, discoveries = collect_context(cwd)
        system_message = build_requirements_message(AnthropicClient.from_env(), context)
        found = ", ".join(discoveries) if discoveries else "no project files"
        status_line = (
            "[plan-enforcer] ✅ AI-generated requirements loaded. "
            f"Discovered {found} in {Path(cwd).name}. "
            "Tailored verification, branch-prep, and doc-update tasks accordingly.\n"
            "--- injected into context ---\n"
            f"{system_message}"
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "systemMessage": (
                "[plan-enforcer] ❌ Failed to generate requirements — skipping. "
                f"{type(exc).__name__}: {exc}"
            )
        }))
        return

    emit(hook_event, system_message, status_line)


if __name__ == "__main__":
    main()
