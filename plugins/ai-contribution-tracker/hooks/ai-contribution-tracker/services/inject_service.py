"""Inject service for AI contribution tracking."""

import re
import subprocess
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

    def process_commit(self, command: str) -> InjectResult:
        """Process a git commit command.

        Args:
            command: Bash command that was executed

        Returns:
            InjectResult with success status and AI percentage if successful
        """
        # Check if this is a git commit command
        if not command or not re.search(r'\bgit\s+commit\s+', command):
            self._logger.info("Not a git commit command, exiting")
            return InjectResult(False)

        # Skip if already an amend (avoid infinite loop)
        if '--amend' in command:
            self._logger.info("Already an amend command, skipping")
            return InjectResult(False)

        self._logger.info("Git commit command detected")

        # Get current branch
        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return InjectResult(False)

        self._logger.info(f"Current branch: {branch}")

        # Get git root
        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("Could not get git root directory")
            return InjectResult(False)

        # Load tracking data
        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)

        self._logger.info(f"Tracking file: {tracking_repo.tracking_path}")

        tracking = tracking_repo.load()
        if not tracking:
            self._logger.warning("No tracking file found")
            return InjectResult(False, message="ℹ️ No AI contributions tracked yet")

        self._logger.info(f"Loaded tracking data, {len(tracking.files_tracked)} files tracked")

        # Always recalculate merge_base (handles merge/rebase correctly)
        tracking.merge_base = self._git_repo.get_merge_base(
            self._config.base_branches
        )
        self._logger.info(f"merge_base: {tracking.merge_base}")

        # Get diff and calculate stats
        if not tracking.merge_base:
            return InjectResult(False)

        diff = self._git_repo.get_diff(tracking.merge_base)
        stats = self._stats_calculator.calculate(tracking, diff)

        self._logger.info(f"Stats: {stats.ai_lines} AI, {stats.human_lines} human")

        # Update tracking data with stats
        tracking.stats = stats.to_dict()
        tracking.last_updated = datetime.now().isoformat()
        tracking_repo.save(tracking)

        self._logger.info("Tracking file updated with stats")

        # Get last commit message
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%B'],
                capture_output=True,
                text=True,
                check=True
            )
            original_message = result.stdout.strip()
        except subprocess.CalledProcessError:
            return InjectResult(False)

        self._logger.info(f"Original message: {original_message[:50]}...")

        # Format and append stats
        stats_msg = stats.format_message()

        new_message = f"{original_message}\n\n{stats_msg}"

        self._logger.info("New message with stats appended")

        # Amend commit with new message
        try:
            subprocess.run(
                ['git', 'commit', '--amend', '-m', new_message],
                check=True,
                capture_output=True
            )
            self._logger.info("=== Commit amended successfully ===")
            ai_percentage = int(round(stats.ai_percentage))
            return InjectResult(True, ai_percentage)
        except subprocess.CalledProcessError:
            self._logger.error("Failed to amend commit")
            return InjectResult(False, message="❌ Failed to amend commit with AI stats")
