"""Branch sync service for AI contribution tracking."""

from datetime import datetime
from logging import Logger

from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository


class BranchSyncService:
    """Recalculates and persists merge_base after a git merge or rebase.

    Called by the inject hook whenever a merge or rebase command is detected,
    so that the tracking file reflects the updated branch topology immediately
    — without waiting for the next commit.
    """

    def __init__(self, git_repo: GitRepository, config: Configuration, logger: Logger):
        """Initialize branch sync service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._logger = logger

    def handle(self) -> bool:
        """Recalculate merge_base and persist it to the tracking file.

        Returns:
            True if merge_base was updated and saved, False otherwise
        """
        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("BranchSync: could not get current branch")
            return False

        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("BranchSync: could not get git root")
            return False

        sanitized_branch = self._git_repo.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()
        if not tracking:
            self._logger.info("BranchSync: no tracking file — skipping")
            return False

        new_base = self._git_repo.get_merge_base(self._config.base_branches)
        if not new_base:
            self._logger.warning("BranchSync: get_merge_base returned None — skipping")
            return False

        tracking.merge_base = new_base
        tracking.last_updated = datetime.now().isoformat()
        saved = tracking_repo.save(tracking)
        if saved:
            self._logger.info(f"BranchSync: merge_base updated to {new_base[:8]}")
        else:
            self._logger.warning("BranchSync: failed to save tracking file")
        return saved
