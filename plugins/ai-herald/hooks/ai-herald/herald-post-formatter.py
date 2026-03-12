#!/usr/bin/env python3
"""
PostToolUse hook for AI contribution tracker - Format Attribution

This hook runs AFTER formatting commands execute. It loads the pre-format
snapshot, compares with current state using token matching, and updates
tracking data to preserve AI attribution through formatting changes.

Hook Event: PostToolUse Bash
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


class FormatPostHook(CommandHookRunner):
    hook_name = 'FORMAT-POST'

    def _handle_code_formatter(self, provider: DependencyProvider, _command: str):
        return provider.build_format_tracker_service().process_post_format()

    command_handlers = {DetectedCommand.CODE_FORMATTER: _handle_code_formatter}

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result) -> None:
        if result:
            hook_output.exit_with_success("✓ Format attribution applied")
        else:
            hook_output.exit_with_success()


def main():
    """Main entry point for format post-hook."""
    FormatPostHook().run()


if __name__ == '__main__':
    main()
