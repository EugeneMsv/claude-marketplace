#!/usr/bin/env python3
"""
AI Contribution Tracker - Inject Hook (PostToolUse Bash)

Runs after git commit and amends the commit message with AI contribution stats.
Part of the ai-contribution-tracker system.
"""

import sys
import json
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from services.bash_command_detector import DetectedCommand


def main():
    """Main hook execution: run after git commit and amend with stats."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider('INJECT')

    try:
        hook_input = json.load(sys.stdin)
        tool_input = hook_input.get('tool_input', {})
        command = tool_input.get('command', '')

        # Early exit: only handle git commit and git push (recovery path)
        detected = provider.bash_command_detector().detect_commands(command)
        if DetectedCommand.GIT_COMMIT not in detected and DetectedCommand.GIT_PUSH not in detected:
            hook_output.exit_with_success()

        if not provider.config().enabled:
            provider.logger().info("AI tracker disabled in config")
            hook_output.exit_with_success()

        service = provider.build_inject_service()

        if DetectedCommand.GIT_COMMIT in detected:
            provider.logger().info("Git commit command detected")
            result = service.process_commit()
        else:
            # Recovery path: push after failed chained commit
            result = service.recover_missed_commit()

        # Run housekeeping if enabled
        if provider.config().housekeeping_enabled:
            try:
                housekeeping = provider.build_housekeeping_service()
                cleanup_result = housekeeping.cleanup_stale_tracking_files()
                provider.logger().info(
                    f"Housekeeping: deleted={cleanup_result.files_deleted}, "
                    f"skipped={cleanup_result.files_skipped}, errors={cleanup_result.files_errored}"
                )
            except Exception as e:
                # Never fail inject flow due to housekeeping
                provider.logger().warning(f"Housekeeping failed: {e}")

        if provider.config().enable_logging:
            if result.success:
                provider.logger().info("Commit amended successfully")
            else:
                provider.logger().info("Skipped (not applicable)")

        if result.message:
            hook_output.exit_with_success(result.message)
        elif result.success and result.ai_percentage is not None:
            hook_output.exit_with_success(f"✓ Commit amended: {result.ai_percentage}% AI")

    except Exception as e:
        try:
            if provider.config().enable_logging:
                provider.logger().error(f"Hook failed: {e}", exc_info=True)
        except:
            pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
