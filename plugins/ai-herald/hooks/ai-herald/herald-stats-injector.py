#!/usr/bin/env python3
"""
AI Contribution Tracker - Inject Hook (PostToolUse Bash)

Runs after git commit/push/merge/rebase and handles each in positional order:
  - GIT_COMMIT  → amend commit message with AI stats
  - GIT_PUSH    → recovery path for missed commits
  - GIT_MERGE / GIT_REBASE → refresh merge_base in tracking file
Part of the ai-contribution-tracker system.
"""

import sys
import json
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import run_hook
from services.bash_command_detector import DetectedCommand
from services.inject_service import InjectResult


def _handle(provider: DependencyProvider, hook_output: HookOutputService) -> None:
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    ordered = provider.bash_command_detector().detect_commands_ordered(command)

    # Early exit: nothing we care about
    actionable = {DetectedCommand.GIT_COMMIT, DetectedCommand.GIT_PUSH,
                  DetectedCommand.GIT_MERGE, DetectedCommand.GIT_REBASE}
    if not any(cmd in actionable for cmd in ordered):
        hook_output.exit_with_success()

    inject_service = provider.build_inject_service()
    inject_result: InjectResult = InjectResult(False)

    for cmd in ordered:
        if cmd == DetectedCommand.GIT_COMMIT:
            provider.logger().info("Git commit command detected")
            inject_result = inject_service.process_commit()

        elif cmd == DetectedCommand.GIT_PUSH:
            # Recovery path: push after failed chained commit
            recovery = inject_service.recover_missed_commit()
            if recovery.success:
                inject_result = recovery

        elif cmd in (DetectedCommand.GIT_MERGE, DetectedCommand.GIT_REBASE):
            provider.logger().info(f"{cmd.value} detected — refreshing merge_base")
            try:
                provider.build_branch_sync_service().handle()
            except Exception as e:
                provider.logger().warning(f"BranchSync failed: {e}")

    # Append to history if inject succeeded and history is enabled
    if inject_result.success and inject_result.stats is not None and inject_result.tracking is not None:
        if provider.config().history_enabled:
            try:
                history_service = provider.build_history_append_service()
                history_service.append_commit(inject_result.stats, inject_result.tracking)
            except Exception as e:
                provider.logger().warning(f"History append failed: {e}")

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
        if inject_result.success:
            provider.logger().info("Commit amended successfully")
        else:
            provider.logger().info("Skipped (not applicable)")

    if inject_result.message:
        hook_output.exit_with_success(inject_result.message)
    elif inject_result.success and inject_result.ai_percentage is not None:
        hook_output.exit_with_success(f"✓ Commit amended: {inject_result.ai_percentage}% AI")


def main():
    """Main hook execution: run after git commit and amend with stats."""
    run_hook('INJECT', _handle)


if __name__ == '__main__':
    main()
