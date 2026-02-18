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

from infrastructure.configuration import ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.glab_repository import GlabRepository
from infrastructure.hook_logger import setup_hook_logger
from infrastructure.hook_output_service import HookOutputService
from services.mr_service import MrService


def main():
    """Main hook execution: run after git push and update MR title with stats."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)

    try:
        # Load configuration
        config = ConfigurationLoader.load()

        # Setup logging with hook prefix and traceId
        log_path = ConfigurationLoader.resolve_log_path(config)
        logger, trace_id = setup_hook_logger('MR-UPDATE', log_path, config.enable_logging)

        # Check if feature is enabled
        if not config.enabled:
            logger.info("AI tracker disabled in config")
            hook_output.exit_with_success()

        if not config.mr_title_update_enabled and not config.mr_auto_creation_enabled and not config.mr_labeling_enabled:
            logger.info("MR title update, auto-creation, and labeling all disabled in config")
            hook_output.exit_with_success()

        # Read hook input
        hook_input = json.load(sys.stdin)
        tool_input = hook_input.get('tool_input', {})
        command = tool_input.get('command', '')

        # Create service instances
        git_repo = GitRepository()
        glab_repo = GlabRepository(logger)
        service = MrService(git_repo, glab_repo, config, logger)

        # Process push
        result = service.process_push(command)

        if config.enable_logging:
            if result.success:
                logger.info("MR updated successfully")
            else:
                logger.info("Skipped (not applicable)")

        # Show user message if available
        if result.message:
            hook_output.exit_with_success(result.message)
        elif result.success and result.ai_percentage is not None:
            hook_output.exit_with_success(f"✓ MR title updated: {result.ai_percentage}% AI")

    except Exception as e:
        try:
            config = ConfigurationLoader.load()
            if config.enable_logging:
                log_path = ConfigurationLoader.resolve_log_path(config)
                error_logger, _ = setup_hook_logger('MR-UPDATE', log_path, True)
                error_logger.error(f"Hook failed: {e}", exc_info=True)
        except:
            pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
