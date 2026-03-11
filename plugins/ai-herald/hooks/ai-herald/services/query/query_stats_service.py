"""Query stats service for on-demand AI contribution statistics."""

from logging import Logger
from typing import Optional

from domain.contribution_stats import ContributionStats
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository
from services.stats_calculator import StatsCalculator


class QueryStatsService:
    """Service for querying current branch AI contribution statistics.

    Extracts the stats-calculation portion of InjectService._do_inject()
    without performing any git amend. Safe to call at any time — read-only.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        stats_calculator: StatsCalculator,
        logger: Logger
    ):
        """Initialize query stats service.

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

    def calculate_current_stats(self) -> Optional[ContributionStats]:
        """Calculate contribution statistics for the current branch.

        Read-only — does not amend commits or write tracking files.

        Returns:
            ContributionStats if stats could be calculated, None when:
            - not in a git repo
            - no current branch
            - no tracking file for the branch
            - no merge base could be computed
        """
        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.debug("Could not get current branch")
            return None

        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.debug("Could not get git root")
            return None

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()
        if not tracking:
            self._logger.debug("No tracking file found for branch: %s", branch)
            return None

        merge_base = self._git_repo.get_merge_base(self._config.base_branches)
        if not merge_base:
            self._logger.debug("No merge base found")
            return None

        diff = self._git_repo.get_diff(merge_base)
        return self._stats_calculator.calculate(tracking, diff)
