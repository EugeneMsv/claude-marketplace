#!/usr/bin/env python3
"""
PostToolUse hook for AI contribution tracker - Format Attribution

This hook runs AFTER formatting commands execute. It loads the pre-format
snapshot, compares with current state using token matching, and updates
tracking data to preserve AI attribution through formatting changes.

Hook Event: PostToolUse Bash
Matcher: spotlessApply|prettier|ruff|eslint.*--fix|gofmt|rustfmt|clang-format
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import HookRunner


class FormatPostHook(HookRunner):
    hook_name = 'FORMAT-POST'

    def _handle(self, provider: DependencyProvider, hook_output: HookOutputService) -> None:
        json.load(sys.stdin)  # consume stdin (unused)

        success = provider.build_format_tracker_service().process_post_format()

        if success:
            if provider.config().enable_logging:
                provider.logger().info("Successfully updated attribution after formatting")
            hook_output.exit_with_success("✓ Format attribution applied")


def main():
    """Main entry point for format post-hook."""
    FormatPostHook().run()


if __name__ == '__main__':
    main()
