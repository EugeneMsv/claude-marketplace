#!/usr/bin/env python3
"""
PostToolUse hook for AI herald - Bash File Deletion Tracking

This hook runs AFTER every Bash command. It inspects the command for rm,
git rm, and unlink patterns, cross-references against git-deleted files, and
marks any matched files as AI-deleted in the tracking data.

Hook Event: PostToolUse Bash
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import CommandHookRunner
from services.bash_command_detector import DetectedCommand


class BashDeleteHook(CommandHookRunner):
    hook_name = 'BASH-DELETE'

    def _handle_bash_deletion(self, provider: DependencyProvider, command: str):
        return provider.build_deletion_tracker_service().process(command)

    command_handlers = {DetectedCommand.BASH_FILE_DELETION: _handle_bash_deletion}

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result) -> None:
        if result:
            hook_output.exit_with_success(f"✓ {len(result)} file(s) marked AI-deleted")
        else:
            hook_output.exit_with_success()


def main():
    """Main entry point for bash delete hook."""
    BashDeleteHook().run()


if __name__ == '__main__':
    main()
