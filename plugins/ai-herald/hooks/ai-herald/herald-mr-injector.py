#!/usr/bin/env python3
"""
AI Contribution Tracker - MR Update Hook (PostToolUse Bash)

Runs after git push and updates GitLab MR title with compact AI contribution stats.
Reads pre-calculated stats from tracking data (written by inject hook on commit).
Part of the ai-contribution-tracker system.
"""

import sys
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import CommandHookRunner
from services.bash_command_detector import DetectedCommand


class MrInjectorHook(CommandHookRunner):
    hook_name = 'MR-UPDATE'

    def _handle_git_push(self, provider: DependencyProvider, _command: str):
        return provider.build_mr_service().process_push()

    command_handlers = {DetectedCommand.GIT_PUSH: _handle_git_push}

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result) -> None:
        if result is None:
            hook_output.exit_with_success()
            return

        if result.message:
            hook_output.exit_with_success(result.message)
        elif result.success and result.ai_percentage is not None:
            hook_output.exit_with_success(f"✓ MR updated: {result.ai_percentage}% AI")
        else:
            hook_output.exit_with_success()


def main():
    """Main hook execution: run after git push and update MR title with stats."""
    MrInjectorHook().run()


if __name__ == '__main__':
    main()
