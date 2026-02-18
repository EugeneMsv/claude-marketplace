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

from domain.line_hasher import LineHasher
from infrastructure.configuration import ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.hook_logger import setup_hook_logger
from infrastructure.hook_output_service import HookOutputService
from services.format_snapshot_service import FormatSnapshotService


def main():
    """Main entry point for format pre-hook."""
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
        logger, trace_id = setup_hook_logger('FORMAT-PRE', log_path, config.enable_logging)

        # Check if tracker is enabled
        if not config.enabled:
            hook_output.exit_with_success()

        # Initialize dependencies
        git_repo = GitRepository()
        hasher = LineHasher()
        snapshot_service = FormatSnapshotService(git_repo, config, hasher, logger)

        # Capture pre-format state
        snapshot_path = snapshot_service.capture_pre_format(command, pid)

        if snapshot_path:
            if config.enable_logging:
                logger.info(f"Created format snapshot: {snapshot_path}")
            hook_output.exit_with_success("⏳ Format snapshot captured")

        # Always allow the command to proceed
        hook_output.exit_with_success()

    except Exception as e:
        # Silent failure - never block user operations
        if '--debug' in sys.argv:
            print(f"Error in format pre-hook: {e}", file=sys.stderr)
        hook_output.exit_with_success()


if __name__ == '__main__':
    main()
