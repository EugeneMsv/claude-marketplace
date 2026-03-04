#!/usr/bin/env python3
"""
PostToolUse hook for AI herald - Bash File Deletion Tracking

This hook runs AFTER every Bash command. It inspects the command for rm,
git rm, and unlink patterns, cross-references against git-deleted files, and
marks any matched files as AI-deleted in the tracking data.

Hook Event: PostToolUse Bash
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import run_hook
from services.bash_command_detector import DetectedCommand


def _handle(provider: DependencyProvider, hook_output: HookOutputService) -> None:
    input_data = json.load(sys.stdin)
    command = input_data.get('tool_input', {}).get('command', '')

    if DetectedCommand.BASH_FILE_DELETION not in provider.bash_command_detector().detect_commands(command):
        hook_output.exit_with_success()

    targets = provider.deletion_targets_detector().detect(command)
    deleted = provider.build_deletion_tracker_service().process(targets)

    if deleted:
        hook_output.exit_with_success(f"✓ {len(deleted)} file(s) marked AI-deleted")
    else:
        hook_output.exit_with_success()


def main():
    """Main entry point for bash delete hook."""
    run_hook('BASH-DELETE', _handle)


if __name__ == '__main__':
    main()
