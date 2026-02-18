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

from domain.line_hasher import LineHasher
from domain.token_normalizer import TokenNormalizer
from infrastructure.configuration import ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.hook_logger import setup_hook_logger
from infrastructure.hook_output_service import HookOutputService
from services.format_tracker_service import FormatTrackerService


def main():
    """Main entry point for format post-hook."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)

    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)

        # Extract command
        tool_input = input_data.get('tool_input', {})
        command = tool_input.get('command', '')

        if not command:
            # No command, nothing to do
            hook_output.exit_with_success()

        # Get PID from environment or use current process
        pid = os.getppid()  # Parent process ID (the bash command)

        # Load configuration
        config = ConfigurationLoader.load()

        # Setup logging with hook prefix and traceId
        log_path = ConfigurationLoader.resolve_log_path(config)
        logger, trace_id = setup_hook_logger('FORMAT-POST', log_path, config.enable_logging)

        # Check if tracker is enabled
        if not config.enabled:
            hook_output.exit_with_success()

        # Initialize dependencies
        git_repo = GitRepository()
        hasher = LineHasher()
        token_normalizer = TokenNormalizer()
        tracker_service = FormatTrackerService(git_repo, config, hasher, token_normalizer, logger)

        # Process post-format state and update attribution
        success = tracker_service.process_post_format(command, pid)

        if success:
            if config.enable_logging:
                logger.info("Successfully updated attribution after formatting")
            hook_output.exit_with_success("✓ Format attribution applied")

        # Always exit successfully - never block user
        hook_output.exit_with_success()

    except Exception as e:
        # Silent failure - never block user operations
        if '--debug' in sys.argv:
            print(f"Error in format post-hook: {e}", file=sys.stderr)
        hook_output.exit_with_success()


if __name__ == '__main__':
    main()
