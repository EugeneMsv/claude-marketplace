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
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import CommandHookRunner
from services.bash_command_detector import DetectedCommand
from services.inject_service import InjectResult


class StatsInjectorHook(CommandHookRunner):
    hook_name = 'INJECT'

    def _handle_git_commit(self, provider: DependencyProvider, _command: str):
        return provider.inject_service().process_commit()

    def _handle_git_push(self, provider: DependencyProvider, _command: str):
        recovery = provider.inject_service().recover_missed_commit()
        return recovery if recovery.success else None

    def _handle_branch_sync(self, provider: DependencyProvider, _command: str):
        try:
            provider.build_branch_sync_service().handle()
        except Exception as e:
            provider.logger().warning(f"BranchSync failed: {e}")

    command_handlers = {
        DetectedCommand.GIT_COMMIT:  _handle_git_commit,
        DetectedCommand.GIT_PUSH:    _handle_git_push,
        DetectedCommand.GIT_MERGE:   _handle_branch_sync,
        DetectedCommand.GIT_REBASE:  _handle_branch_sync,
    }

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result) -> None:
        inject_result = result if result is not None else InjectResult(False)

        if inject_result.success and inject_result.stats is not None and inject_result.tracking is not None:
            if provider.config().history_enabled:
                try:
                    provider.build_history_append_service().append_commit(
                        inject_result.stats, inject_result.tracking
                    )
                except Exception as e:
                    provider.logger().warning(f"History append failed: {e}")

        if provider.config().housekeeping_enabled:
            try:
                housekeeping = provider.build_housekeeping_service()
                cleanup_result = housekeeping.cleanup_stale_tracking_files()
                provider.logger().info(
                    f"Housekeeping: deleted={cleanup_result.files_deleted}, "
                    f"skipped={cleanup_result.files_skipped}, errors={cleanup_result.files_errored}"
                )
            except Exception as e:
                provider.logger().warning(f"Housekeeping failed: {e}")

        if inject_result.message:
            hook_output.exit_with_success(inject_result.message)
        elif inject_result.success and inject_result.ai_percentage is not None:
            hook_output.exit_with_success(f"✓ Commit amended: {inject_result.ai_percentage}% AI")
        else:
            hook_output.exit_with_success()


def main():
    """Main hook execution: run after git commit and amend with stats."""
    StatsInjectorHook().run()


if __name__ == '__main__':
    main()
