#!/usr/bin/env python3
"""
PreToolUse hook for AI contribution tracker - Format Detection

This hook runs BEFORE formatting commands execute. It captures the current
state of tracked files so they can be compared with post-format state to
preserve AI attribution through formatting changes.

Hook Event: PreToolUse Bash
Matcher: spotlessApply|prettier|ruff|eslint.*--fix|gofmt|rustfmt|clang-format
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import CommandHookRunner
from services.bash_command_detector import DetectedCommand


class FormatPreHook(CommandHookRunner):
    hook_name = 'FORMAT-PRE'

    def _handle_code_formatter(self, provider: DependencyProvider, _command: str):
        if not provider.config().format_detection_enabled:
            return None
        return provider.build_format_snapshot_service().capture_pre_format()

    command_handlers = {DetectedCommand.CODE_FORMATTER: _handle_code_formatter}

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result) -> None:
        if result:
            if provider.config().enable_logging:
                provider.logger().info(f"Created format snapshot: {result}")
            hook_output.exit_with_success("⏳ Format snapshot captured")
        else:
            hook_output.exit_with_success()


def main():
    """Main entry point for format pre-hook."""
    FormatPreHook().run()


if __name__ == '__main__':
    main()
