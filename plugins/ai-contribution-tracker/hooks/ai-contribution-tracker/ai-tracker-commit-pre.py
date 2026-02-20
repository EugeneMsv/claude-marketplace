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

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.tracking_repository import TrackingRepository
from infrastructure.git_repository import GitRepository
from services.bash_command_detector import DetectedCommand


def main():
    """Record commit intent before a git commit command runs."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider('COMMIT-PRE')

    try:
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

        git_repo = provider.git_repo()
        git_root = git_repo.get_root()
        branch = git_repo.get_current_branch()

        if not git_root or not branch:
            hook_output.exit_with_success()

        sanitized_branch_name = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch_name)
        tracking = tracking_repo.load()

        if not tracking:
            # No tracking data yet — nothing to recover
            hook_output.exit_with_success()

        head_hash = git_repo.get_head_commit_hash()
        if not head_hash:
            hook_output.exit_with_success()

        tracking.pending_inject_head = head_hash
        tracking_repo.save(tracking)

        provider.logger().info(f"Commit intent recorded: head_before={head_hash[:8]}")

    except Exception:
        # Never block the user's command
        pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
