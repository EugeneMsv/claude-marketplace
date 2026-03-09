"""Inject service for AI contribution tracking."""

from datetime import datetime
from logging import Logger
from typing import Optional
from domain.tracking_data import TrackingData
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository
from services.stats_calculator import StatsCalculator


class InjectResult:
    """Result of processing a git commit."""

    def __init__(self, success: bool, ai_percentage: Optional[int] = None, message: Optional[str] = None):
        """Initialize inject result.

        Args:
            success: Whether commit was successfully amended
            ai_percentage: AI contribution percentage (0-100), None if failed
            message: Optional informational message to show user
        """
        self.success = success
        self.ai_percentage = ai_percentage
        self.message = message


class InjectService:
    """Service coordinating the inject hook workflow.

    Processes git commit events to calculate stats and amend commit messages.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        stats_calculator: StatsCalculator,
        logger: Logger
    ):
        """Initialize inject service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            stats_calculator: StatsCalculator for computing statistics
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._stats_calculator = stats_calculator
        self._logger = logger

    def process_commit(self) -> InjectResult:
        """Inject AI contribution stats into the current HEAD commit.

        Caller is responsible for ensuring this is only invoked for a non-amend
        git commit command.

        Returns:
            InjectResult with success status and AI percentage if successful
        """
        self._logger.info("Processing commit injection")

        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return InjectResult(False)

        self._logger.info(f"Current branch: {branch}")

        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("Could not get git root directory")
            return InjectResult(False)

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)

        self._logger.info(f"Tracking file: {tracking_repo.tracking_path}")

        tracking = tracking_repo.load()
        if not tracking:
            self._logger.warning("No tracking file found")
            return InjectResult(False, message="ℹ️ No AI contributions tracked yet")

        self._logger.info(f"Loaded tracking data, {len(tracking.files_tracked)} files tracked")

        return self._do_inject(tracking, tracking_repo)

    def recover_missed_commit(self) -> InjectResult:
        """Recover injection for a commit that was missed due to chained command failure.

        When a chained bash command like `git add && git commit && git push` fails
        at the push step, PostToolUse is never dispatched. The pre-hook recorded the
        HEAD hash before the commit ran. This method detects the discrepancy and
        injects stats into the now-existing commit.

        Returns:
            InjectResult with success status if recovery injected, otherwise False
        """
        git_root = self._git_repo.get_root()
        if not git_root:
            return InjectResult(False)

        branch = self._git_repo.get_current_branch()
        if not branch:
            return InjectResult(False)

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()

        if not tracking:
            return InjectResult(False)

        pending = tracking.pending_inject_head
        if not pending:
            # No commit intent was recorded — nothing to recover
            return InjectResult(False)

        current_head = self._git_repo.get_head_commit_hash()

        if pending == current_head:
            # HEAD didn't change — the commit step never succeeded
            tracking.pending_inject_head = None
            tracking_repo.save(tracking)
            self._logger.info("Commit intent present but HEAD unchanged — commit failed, clearing flag")
            return InjectResult(False)

        commit_message = self._git_repo.get_head_commit_message()
        if commit_message and "Overall: +" in commit_message:
            # Already injected (e.g. normal path ran on a later call)
            tracking.pending_inject_head = None
            tracking_repo.save(tracking)
            self._logger.info("Commit already has stats, clearing flag")
            return InjectResult(False)

        self._logger.info(f"Recovering missed inject: head_before={pending[:8]}, head_now={current_head[:8] if current_head else '?'}")
        result = self._do_inject(tracking, tracking_repo)
        if result.success:
            self._logger.info("=== Recovered missed commit injection ===")
        return result

    def record_commit_intent(self) -> None:
        """Record HEAD hash before a commit runs to enable missed-commit recovery.

        Called by the PreToolUse hook before a non-amend git commit executes.
        Stores the current HEAD in pending_inject_head so recover_missed_commit
        can detect if the commit succeeded but PostToolUse was skipped.
        """
        git_root = self._git_repo.get_root()
        branch = self._git_repo.get_current_branch()
        if not git_root or not branch:
            return

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()
        if not tracking:
            return

        head_hash = self._git_repo.get_head_commit_hash()
        if not head_hash:
            return

        tracking.pending_inject_head = head_hash
        tracking_repo.save(tracking)
        self._logger.info(f"Commit intent recorded: head_before={head_hash[:8]}")

    def _do_inject(self, tracking: TrackingData, tracking_repo: TrackingRepository) -> InjectResult:
        """Calculate stats and amend the current HEAD commit message.

        Shared by both process_commit and recover_missed_commit. Clears
        pending_inject_head on completion (success or failure after stats save).

        Args:
            tracking: Loaded TrackingData to use and update
            tracking_repo: Repository to persist updated tracking data

        Returns:
            InjectResult with success status and AI percentage
        """
        # Always recalculate merge_base (handles merge/rebase correctly)
        tracking.merge_base = self._git_repo.get_merge_base(self._config.base_branches)
        self._logger.info(f"merge_base: {tracking.merge_base}")

        if not tracking.merge_base:
            return InjectResult(False)

        diff = self._git_repo.get_diff(tracking.merge_base)
        stats = self._stats_calculator.calculate(tracking, diff)

        ignored = stats.ignored_files
        self._logger.info(f"Stats: {stats.ai_lines} AI, {stats.human_lines} human, {ignored.total} ignored")
        if ignored.total > 0:
            self._logger.info(f"Ignored matched patterns: {sorted(ignored.matched_patterns)}")

        # Update tracking data with stats and clear commit intent flag
        tracking.stats = stats.to_dict()
        tracking.last_updated = datetime.now().isoformat()
        tracking.pending_inject_head = None
        tracking_repo.save(tracking)

        self._logger.info("Tracking file updated with stats")

        original_message = self._git_repo.get_head_commit_message()
        if not original_message:
            return InjectResult(False)

        self._logger.info(f"Original message: {original_message[:50]}...")

        stats_msg = stats.format_message()
        new_message = f"{original_message}\n\n{stats_msg}"

        self._logger.info("New message with stats appended")

        if self._git_repo.amend_commit_message(new_message):
            self._logger.info("=== Commit amended successfully ===")
            ai_percentage = int(round(stats.ai_percentage))
            return InjectResult(True, ai_percentage)
        else:
            self._logger.error("Failed to amend commit")
            return InjectResult(False, message="❌ Failed to amend commit with AI stats")
