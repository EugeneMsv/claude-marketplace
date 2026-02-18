#!/usr/bin/env python3
"""
AI Contribution Tracker - Inject Hook (PostToolUse Bash) - OOP Version

Runs after git commit and amends the commit message with AI contribution stats.
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
from services.stats_calculator import StatsCalculator
from services.inject_service import InjectService


def main():
    """Main hook execution: run after git commit and amend with stats."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)

    try:
        # Load configuration
        config = ConfigurationLoader.load()

        # Setup logging with hook prefix and traceId
        log_path = ConfigurationLoader.resolve_log_path(config)
        logger, trace_id = setup_hook_logger('INJECT', log_path, config.enable_logging)

        # Check if feature is enabled
        if not config.enabled:
            logger.info("AI tracker disabled in config")
            hook_output.exit_with_success()

        # Read hook input
        hook_input = json.load(sys.stdin)
        tool_input = hook_input.get('tool_input', {})
        command = tool_input.get('command', '')

        # Create service instances
        git_repo = GitRepository()
        hasher = LineHasher()
        stats_calculator = StatsCalculator(hasher)
        service = InjectService(git_repo, config, stats_calculator, logger)

        # Process commit
        result = service.process_commit(command)

        # Run housekeeping if enabled
        if config.housekeeping_enabled:
            try:
                from services.housekeeping_service import HousekeepingService
                housekeeping = HousekeepingService(git_repo, config, logger)
                cleanup_result = housekeeping.cleanup_stale_tracking_files()
                logger.info(
                    f"Housekeeping: deleted={cleanup_result.files_deleted}, "
                    f"skipped={cleanup_result.files_skipped}, errors={cleanup_result.files_errored}"
                )
            except Exception as e:
                # Never fail inject flow due to housekeeping
                logger.warning(f"Housekeeping failed: {e}")

        if config.enable_logging:
            if result.success:
                logger.info("Commit amended successfully")
            else:
                logger.info("Skipped (not applicable)")

        # Show user message if available
        if result.message:
            hook_output.exit_with_success(result.message)
        elif result.success and result.ai_percentage is not None:
            hook_output.exit_with_success(f"✓ Commit amended: {result.ai_percentage}% AI")

    except Exception as e:
        try:
            config = ConfigurationLoader.load()
            if config.enable_logging:
                log_path = ConfigurationLoader.resolve_log_path(config)
                error_logger, _ = setup_hook_logger('INJECT', log_path, True)
                error_logger.error(f"Hook failed: {e}", exc_info=True)
        except:
            pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
