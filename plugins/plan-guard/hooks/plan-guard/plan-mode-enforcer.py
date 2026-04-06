#!/usr/bin/env python3
"""PreToolUse hook for EnterPlanMode — injects project-specific planning requirements."""

import json
import os
import sys
from pathlib import Path

FALLBACK_MESSAGE = (
    "Planning requirements for this session:\n"
    "• Every task MUST include a verification step with the project's test command\n"
    "• Every task MUST end with an explicit git commit: \"Task N: <description>\"\n"
    "• The LAST task MUST run the full test suite "
    "(unit + integration + e2e/UAT/smoke as applicable) "
    "AND update relevant documentation before its commit"
)

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
}

PROMPT_TEMPLATE = """\
You are a planning assistant for a software engineer. Based on the project context below, \
produce a concise systemMessage (3–5 bullet points, plain text) that the engineer will see \
when entering plan mode. The message must specify:

1. The exact verification command(s) for this project that EVERY task must run
2. That every task must end with a git commit in format "Task N: <description>"
3. That the LAST task must run ALL available verifications \
(unit + integration + e2e/UAT/smoke as applicable) AND update relevant documentation

Be specific — use the actual commands from the project context. If you cannot determine \
the exact command, use a sensible default for the detected build tool.
Output ONLY the bullet-point message, no preamble.

PROJECT CONTEXT:
{context}
"""


def collect_context(cwd: str) -> str:
    base = Path(cwd)
    parts = []

    # Detected build tools
    found_tools = [label for fname, label in BUILD_FILE_HINTS.items() if (base / fname).exists()]
    if found_tools:
        parts.append(f"Build tools: {', '.join(found_tools)}")

    # CLAUDE.md or .claude/CLAUDE.md — first 60 lines
    for candidate in [base / "CLAUDE.md", base / ".claude" / "CLAUDE.md"]:
        if candidate.exists():
            try:
                lines = candidate.read_text(errors="ignore").splitlines()[:60]
                parts.append("CLAUDE.md:\n" + "\n".join(lines))
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
            except OSError:
                pass
            break

    return "\n\n".join(parts)[:1200]


def call_anthropic(context: str) -> str:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    model = os.environ.get(
        "ANTHROPIC_MODEL",
        "claude-haiku-4-5-20251001",
    )
    response = client.messages.create(
        model=model,
        max_tokens=350,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(context=context)}],
    )
    return response.content[0].text.strip()


def main() -> None:
    hook_input = json.load(sys.stdin)
    hook_event = hook_input.get("hook_event_name", "PreToolUse")
    cwd = hook_input.get("cwd", os.getcwd())

    # For UserPromptSubmit, only activate when actually in plan mode
    if hook_event == "UserPromptSubmit" and hook_input.get("permission_mode") != "plan":
        print("{}")
        return

    try:
        context = collect_context(cwd)
        if context:
            system_message = call_anthropic(context)
            status_line = "[plan-enforcer] ✅ AI-generated requirements loaded for this project"
        else:
            system_message = FALLBACK_MESSAGE
            status_line = "[plan-enforcer] ⚠️ No project context found — using fallback defaults"
    except Exception:  # noqa: BLE001
        system_message = FALLBACK_MESSAGE
        status_line = "[plan-enforcer] ❌ Failed to generate requirements — using fallback defaults"

    output = {
        "systemMessage": status_line,
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": system_message,
        },
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
