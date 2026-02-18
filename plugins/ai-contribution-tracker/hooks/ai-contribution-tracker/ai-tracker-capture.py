#!/usr/bin/env python3
"""
AI Contribution Tracker - Capture Hook (PostToolUse Write/Edit) - OOP Version

Records AI-authored line hashes to track AI vs human contributions.
Part of the ai-contribution-tracker system.
"""

import sys
import json
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import OOP components
from infrastructure.configuration import ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.hook_logger import setup_hook_logger
from infrastructure.hook_output_service import HookOutputService
from domain.line_hasher import LineHasher
from services.capture_service import CaptureService


def main():
    """Main hook execution."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)

    try:
        # Load configuration
        config = ConfigurationLoader.load()

        # Setup logging with hook prefix and traceId
        log_path = ConfigurationLoader.resolve_log_path(config)
        logger, trace_id = setup_hook_logger('CAPTURE', log_path, config.enable_logging)

        # Check if feature is enabled
        if not config.enabled:
            logger.info("AI tracker disabled in config")
            hook_output.exit_with_success()

        # Read hook input from stdin
        hook_input = json.load(sys.stdin)

        # Create service instances
        git_repo = GitRepository()
        hasher = LineHasher()
        service = CaptureService(git_repo, config, hasher, logger)

        # Process tool use
        tool_name = hook_input.get('tool_name')
        tool_input = hook_input.get('tool_input', {})
        success = service.process_tool_use(tool_name, tool_input)

        if config.enable_logging:
            if success:
                logger.info("Successfully processed tool use")
            else:
                logger.info("Skipped (not applicable)")

        # Show user message if tracking succeeded
        if success:
            file_path = tool_input.get('file_path', '')
            if file_path:
                file_name = Path(file_path).name
                hook_output.exit_with_success(f"✓ AI contribution tracked: {file_name}")

    except Exception as e:
        # Never block operations - silently fail
        try:
            config = ConfigurationLoader.load()
            if config.enable_logging:
                log_path = ConfigurationLoader.resolve_log_path(config)
                error_logger, _ = setup_hook_logger('CAPTURE', log_path, True)
                error_logger.error(f"Hook failed: {e}", exc_info=True)
        except:
            pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
