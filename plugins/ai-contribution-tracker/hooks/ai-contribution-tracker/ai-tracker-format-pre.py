#!/usr/bin/env python3
"""
PreToolUse hook for AI contribution tracker - Format Detection

This hook runs BEFORE formatting commands execute. It captures the current
state of tracked files so they can be compared with post-format state to
preserve AI attribution through formatting changes.

Hook Event: PreToolUse Bash
Matcher: spotlessApply|prettier|black|eslint.*--fix|gofmt|rustfmt|clang-format
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from services.bash_command_detector import DetectedCommand


def main():
    """Main entry point for format pre-hook."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider('FORMAT-PRE')

    try:
        input_data = json.load(sys.stdin)
        tool_input = input_data.get('tool_input', {})
        command = tool_input.get('command', '')

        # Early exit: no command
        if not command:
            hook_output.exit_with_success()

        pid = os.getppid()  # Parent process ID (the bash command)

        # Early exit: tracker disabled or format detection disabled
        config = provider.config()
        if not config.enabled or not config.format_detection_enabled:
            hook_output.exit_with_success()

        # Early exit: not a configured formatter command
        detected = provider.bash_command_detector().detect_commands(command)
        if DetectedCommand.CODE_FORMATTER not in detected:
            hook_output.exit_with_success()

        snapshot_service = provider.build_format_snapshot_service()
        snapshot_path = snapshot_service.capture_pre_format(pid)

        if snapshot_path:
            if config.enable_logging:
                provider.logger().info(f"Created format snapshot: {snapshot_path}")
            hook_output.exit_with_success("⏳ Format snapshot captured")

        hook_output.exit_with_success()

    except Exception as e:
        # Silent failure - never block user operations
        if '--debug' in sys.argv:
            print(f"Error in format pre-hook: {e}", file=sys.stderr)
        hook_output.exit_with_success()


if __name__ == '__main__':
    main()
