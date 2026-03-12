#!/usr/bin/env python3
"""
PreToolUse hook for AI contribution tracker - Commit Intent Recording

Runs BEFORE a git commit command executes. Records the current HEAD hash into
the tracking file so that ai-tracker-inject.py can recover if the commit happens
inside a chained command that fails (e.g. git add && git commit && git push where
push fails) — causing PostToolUse to be skipped entirely.

Hook Event: PreToolUse Bash
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_runner import CommandHookRunner
from services.bash_command_detector import DetectedCommand


class CommitPreHook(CommandHookRunner):
    hook_name = 'COMMIT-PRE'

    def _handle_git_commit(self, provider: DependencyProvider, _command: str):
        provider.build_inject_service().record_commit_intent()

    command_handlers = {DetectedCommand.GIT_COMMIT: _handle_git_commit}


def main():
    """Record commit intent before a git commit command runs."""
    CommitPreHook().run()


if __name__ == '__main__':
    main()
