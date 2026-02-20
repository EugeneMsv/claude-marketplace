#!/usr/bin/env python3
"""
PostToolUse hook for AI contribution tracker - Format Attribution

This hook runs AFTER formatting commands execute. It loads the pre-format
snapshot, compares with current state using token matching, and updates
tracking data to preserve AI attribution through formatting changes.

Hook Event: PostToolUse Bash
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


def main():
    """Main entry point for format post-hook."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider('FORMAT-POST')

    try:
        input_data = json.load(sys.stdin)
        pid = os.getppid()  # Parent process ID (the bash command)

        if not provider.config().enabled:
            hook_output.exit_with_success()

        success = provider.build_format_tracker_service().process_post_format(pid)

        if success:
            if provider.config().enable_logging:
                provider.logger().info("Successfully updated attribution after formatting")
            hook_output.exit_with_success("✓ Format attribution applied")

        hook_output.exit_with_success()

    except Exception as e:
        # Silent failure - never block user operations
        if '--debug' in sys.argv:
            print(f"Error in format post-hook: {e}", file=sys.stderr)
        hook_output.exit_with_success()


if __name__ == '__main__':
    main()
