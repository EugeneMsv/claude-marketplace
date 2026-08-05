#!/usr/bin/env python3
"""UserPromptSubmit hook — reminds the agent that a prompt asking for more than
one thing may warrant splitting into tasks, especially when part of it needs
exploration/research before implementation. Purely static: no model call, no
judgment about whether splitting actually applies here — that decision is left
entirely to the agent handling the prompt.

MUST NOT run when permission_mode == "plan" — that mode is fully owned by the
plan-guard plugin's own UserPromptSubmit hooks.
"""

import json
import sys
from pathlib import Path

REMINDER = (
    "REMINDER (non-binding, may or may not apply here): if this ask covers more than one "
    "thing — especially if part of it requires exploration/research before you can "
    "implement anything — consider splitting it into a numbered Task N: ... breakdown via "
    "TaskCreate before starting. Before creating new tasks, check TaskList for existing "
    "tasks that overlap with this ask; if any are in progress or pending, prefer adding this "
    "work as a subtask of one of those (TaskUpdate addBlockedBy/addBlocks) over creating a "
    "parallel, conflicting task tree. Use your own judgment on whether this prompt actually "
    "needs any of this."
)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def plugin_version() -> str:
    """Read this plugin's own version from its plugin.json, for the status line."""
    try:
        manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
        return manifest.get("version", "unknown")
    except (OSError, json.JSONDecodeError, KeyError):
        return "unknown"


def main() -> None:
    hook_input = json.load(sys.stdin)

    # Hard constraint: this hook is a complete no-op in plan mode — plan-guard owns it.
    if hook_input.get("permission_mode") == "plan":
        print("{}")
        return

    prompt_text = hook_input.get("prompt", "").strip()
    if not prompt_text:
        print("{}")
        return

    print(json.dumps({
        "systemMessage": f"[task-seeder v{plugin_version()}] Task-split reminder applied.",
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": REMINDER,
        },
    }))


if __name__ == "__main__":
    main()
