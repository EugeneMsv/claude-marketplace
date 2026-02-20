#!/usr/bin/env python3
"""
PreToolUse hook for AI contribution tracker - Commit Intent Recording

Runs BEFORE a git commit command executes. Records the current HEAD hash into
the tracking file so that ai-tracker-inject.py can recover if the commit happens
inside a chained command that fails (e.g. git add && git commit && git push where
push fails) — causing PostToolUse to be skipped entirely.

Hook Event: PreToolUse Bash
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import run_hook
from services.bash_command_detector import DetectedCommand


def _handle(provider: DependencyProvider, hook_output: HookOutputService) -> None:
    input_data = json.load(sys.stdin)
    tool_input = input_data.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        hook_output.exit_with_success()

    # Early exit: only act on non-amend git commits
    if DetectedCommand.GIT_COMMIT not in provider.bash_command_detector().detect_commands(command):
        hook_output.exit_with_success()

    if not provider.config().enabled:
        hook_output.exit_with_success()

    provider.build_inject_service().record_commit_intent()


def main():
    """Record commit intent before a git commit command runs."""
    run_hook('COMMIT-PRE', _handle)


if __name__ == '__main__':
    main()
