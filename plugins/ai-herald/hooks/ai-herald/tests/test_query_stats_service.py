"""Tests for QueryStatsService.calculate_current_stats()."""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import ContributionStats, ContributorStats, LineStats
from domain.diff import Diff
from domain.tracking_data import TrackingData
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository
from services.query.query_stats_service import QueryStatsService
from services.stats_calculator import StatsCalculator


def _make_logger():
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    return logger


def _make_config(base_branches=None):
    return Configuration(
        enabled=True,
        base_branches=base_branches or ["main"],
        tracked_extensions={".py"},
        enable_logging=False,
        log_file="test.log",
    )


def _make_stats(ai_pct: float = 80.0) -> ContributionStats:
    ai = ContributorStats(
        total=LineStats(lines=8, percentage=ai_pct),
        added=LineStats(lines=8, percentage=ai_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    human = ContributorStats(
        total=LineStats(lines=2, percentage=100.0 - ai_pct),
        added=LineStats(lines=2, percentage=100.0 - ai_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    return ContributionStats(ai_stats=ai, human_stats=human, by_file_type={})


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_root(temp_dir):
    (temp_dir / ".claude").mkdir()
    return temp_dir


@pytest.fixture
def logger():
    return _make_logger()


@pytest.fixture
def config():
    return _make_config()


@pytest.fixture
def git_repo():
    repo = MagicMock(spec=GitRepository)
    repo.get_current_branch.return_value = "feature-branch"
    repo.get_root.return_value = None  # overridden per test
    repo.get_merge_base.return_value = "merge-base-hash"
    repo.get_diff.return_value = Diff("merge-base-hash", {})
    return repo


@pytest.fixture
def stats_calculator():
    calc = MagicMock(spec=StatsCalculator)
    calc.calculate.return_value = _make_stats()
    return calc


@pytest.fixture
def service(git_repo, config, stats_calculator, logger):
    return QueryStatsService(git_repo, config, stats_calculator, logger)


class TestCalculateCurrentStatsSkipConditions:
    """Tests for all guard conditions in calculate_current_stats."""

    def test_returns_none_when_no_branch(self, service, git_repo):
        """Given branch unavailable, returns None."""
        git_repo.get_current_branch.return_value = None

        result = service.calculate_current_stats()

        assert result is None

    def test_returns_none_when_no_git_root(self, service, git_repo):
        """Given git root unavailable, returns None."""
        git_repo.get_root.return_value = None

        result = service.calculate_current_stats()

        assert result is None

    def test_returns_none_when_no_tracking_file(self, service, git_repo, git_root):
        """Given no tracking file exists, returns None."""
        git_repo.get_root.return_value = git_root

        result = service.calculate_current_stats()

        assert result is None

    def test_returns_none_when_no_merge_base(self, service, git_repo, git_root):
        """Given tracking exists but no merge base, returns None."""
        git_repo.get_root.return_value = git_root
        git_repo.get_merge_base.return_value = None

        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]
        TrackingRepository(git_root, "feature-branch").save(tracking)

        result = service.calculate_current_stats()

        assert result is None


class TestCalculateCurrentStatsSuccess:
    """Tests for successful stats calculation."""

    def test_returns_stats_when_all_data_available(
        self, service, git_repo, git_root
    ):
        """Given all data available, returns ContributionStats."""
        git_repo.get_root.return_value = git_root

        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]
        TrackingRepository(git_root, "feature-branch").save(tracking)

        result = service.calculate_current_stats()

        assert result is not None
        assert isinstance(result, ContributionStats)
        assert result.ai_percentage == 80.0

    def test_passes_tracking_and_diff_to_calculator(
        self, service, git_repo, git_root, stats_calculator
    ):
        """Given valid state, calculator receives tracking data and diff."""
        git_repo.get_root.return_value = git_root
        git_repo.get_merge_base.return_value = "abc123"
        expected_diff = Diff("abc123", {})
        git_repo.get_diff.return_value = expected_diff

        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]
        TrackingRepository(git_root, "feature-branch").save(tracking)

        service.calculate_current_stats()

        call_args = stats_calculator.calculate.call_args
        assert call_args[0][1] is expected_diff

    def test_does_not_modify_tracking_file(self, service, git_repo, git_root):  # noqa: ARG002
        """Given valid state, tracking file is not modified."""
        git_repo.get_root.return_value = git_root

        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        # Capture modification time before
        mtime_before = repo.tracking_path.stat().st_mtime

        service.calculate_current_stats()

        # Tracking file must not be touched
        assert repo.tracking_path.stat().st_mtime == mtime_before

    @pytest.mark.parametrize("branch,sanitized", [
        ("feature/my-feature", "feature-my-feature"),
        ("hotfix/fix-123", "hotfix-fix-123"),
    ])
    def test_sanitizes_branch_name_for_tracking_lookup(
        self, config, stats_calculator, logger, temp_dir, branch, sanitized
    ):
        """Given branch with slashes, uses sanitized name for tracking file lookup."""
        git_root = temp_dir
        (git_root / ".claude").mkdir()

        git_repo = MagicMock(spec=GitRepository)
        git_repo.get_current_branch.return_value = branch
        git_repo.get_root.return_value = git_root
        git_repo.get_merge_base.return_value = "merge-base"
        git_repo.get_diff.return_value = Diff("merge-base", {})

        tracking = TrackingData(branch)
        tracking.files_tracked = ["file.py"]
        TrackingRepository(git_root, sanitized).save(tracking)

        service = QueryStatsService(git_repo, config, stats_calculator, logger)
        result = service.calculate_current_stats()

        assert result is not None
