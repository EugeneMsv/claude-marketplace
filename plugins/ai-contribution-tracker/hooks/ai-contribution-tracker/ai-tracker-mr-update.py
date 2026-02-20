#!/usr/bin/env python3
"""
AI Contribution Tracker - MR Update Hook (PostToolUse Bash)

Runs after git push and updates GitLab MR title with compact AI contribution stats.
Reads pre-calculated stats from tracking data (written by inject hook on commit).
Part of the ai-contribution-tracker system.
"""

import sys
import json
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import run_hook
from services.bash_command_detector import DetectedCommand


def _handle(provider: DependencyProvider, hook_output: HookOutputService) -> None:
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    # Early exit: only handle non-tag git push
    detected = provider.bash_command_detector().detect_commands(command)
    if DetectedCommand.GIT_PUSH not in detected:
        hook_output.exit_with_success()

    if not provider.config().mr_features_enabled:
        provider.logger().info("All MR features disabled in config")
        hook_output.exit_with_success()

    result = provider.build_mr_service().process_push()

    if provider.config().enable_logging:
        if result.success:
            provider.logger().info("MR updated successfully")
        else:
            provider.logger().info("Skipped (not applicable)")

    if result.message:
        hook_output.exit_with_success(result.message)
    elif result.success and result.ai_percentage is not None:
        hook_output.exit_with_success(f"✓ MR updated: {result.ai_percentage}% AI")


def main():
    """Main hook execution: run after git push and update MR title with stats."""
    run_hook('MR-UPDATE', _handle)


if __name__ == '__main__':
    main()
