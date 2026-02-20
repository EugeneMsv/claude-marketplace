"""Tests for InjectService — recover_missed_commit and _do_inject."""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import ContributionStats, ContributorStats, LineStats
from domain.diff import Diff
from domain.tracking_data import TrackingData
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository
from services.inject_service import InjectService, InjectResult
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
    repo.get_head_commit_hash.return_value = "newhead123"
    repo.get_head_commit_message.return_value = "Fix bug"
    return repo


@pytest.fixture
def stats_calculator():
    calc = MagicMock(spec=StatsCalculator)
    calc.calculate.return_value = _make_stats()
    return calc


@pytest.fixture
def service(git_repo, config, stats_calculator, logger):
    return InjectService(git_repo, config, stats_calculator, logger)


class TestRecoverMissedCommitSkipConditions:
    """Tests for all guard conditions in recover_missed_commit."""

    def test_skips_when_no_git_root(self, service, git_repo):
        """Given git root unavailable, returns False."""
        git_repo.get_root.return_value = None

        result = service.recover_missed_commit()

        assert not result.success

    def test_skips_when_no_branch(self, service, git_repo, git_root):
        """Given branch unavailable, returns False."""
        git_repo.get_root.return_value = git_root
        git_repo.get_current_branch.return_value = None

        result = service.recover_missed_commit()

        assert not result.success

    def test_skips_when_no_tracking_file(self, service, git_repo, git_root):
        """Given no tracking file exists, returns False."""
        git_repo.get_root.return_value = git_root

        result = service.recover_missed_commit()

        assert not result.success

    def test_skips_when_no_pending_inject_head(self, service, git_repo, git_root):
        """Given tracking exists but no pending_inject_head, returns False."""
        git_repo.get_root.return_value = git_root
        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = None
        TrackingRepository(git_root, "feature-branch").save(tracking)

        result = service.recover_missed_commit()

        assert not result.success

    def test_skips_when_head_unchanged(self, service, git_repo, git_root):
        """Given pending_inject_head equals current HEAD, commit never happened — clears flag."""
        git_repo.get_root.return_value = git_root
        git_repo.get_head_commit_hash.return_value = "samehash"

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "samehash"
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        result = service.recover_missed_commit()

        assert not result.success
        loaded = repo.load()
        assert loaded.pending_inject_head is None

    def test_skips_when_already_injected(self, service, git_repo, git_root):
        """Given commit message already contains 'Overall: +', clears flag and skips."""
        git_repo.get_root.return_value = git_root
        git_repo.get_head_commit_hash.return_value = "newhead"
        git_repo.get_head_commit_message.return_value = "Fix bug\n\nOverall: +120 -30\nAI: 80%"

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "oldhead"
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        result = service.recover_missed_commit()

        assert not result.success
        loaded = repo.load()
        assert loaded.pending_inject_head is None


class TestRecoverMissedCommitSuccess:
    """Tests for successful recovery injection."""

    def test_injects_when_head_changed(self, service, git_repo, git_root):
        """Given HEAD changed and no existing stats, runs inject and clears flag."""
        git_repo.get_root.return_value = git_root
        git_repo.get_head_commit_hash.return_value = "newhead"
        git_repo.get_head_commit_message.return_value = "Fix bug"

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "oldhead"
        tracking.files_tracked = ["file.py"]
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        git_repo.amend_commit_message.return_value = True

        result = service.recover_missed_commit()

        assert result.success
        assert result.ai_percentage == 80
        loaded = repo.load()
        assert loaded.pending_inject_head is None

    def test_clears_flag_even_when_amend_fails(self, service, git_repo, git_root):
        """Given amend subprocess fails, flag is still cleared (stats were saved before amend)."""
        git_repo.get_root.return_value = git_root
        git_repo.get_head_commit_hash.return_value = "newhead"
        git_repo.get_head_commit_message.return_value = "Fix bug"

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "oldhead"
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        git_repo.amend_commit_message.return_value = False

        result = service.recover_missed_commit()

        assert not result.success
        loaded = repo.load()
        assert loaded.pending_inject_head is None


class TestRecordCommitIntent:
    """Tests for InjectService.record_commit_intent."""

    def test_writes_head_hash_to_tracking(self, service, git_repo, git_root):
        """Given tracking exists and git head available, sets pending_inject_head."""
        git_repo.get_root.return_value = git_root
        git_repo.get_current_branch.return_value = "feature-branch"
        git_repo.get_head_commit_hash.return_value = "abc123"

        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        service.record_commit_intent()

        loaded = repo.load()
        assert loaded.pending_inject_head == "abc123"

    def test_skips_when_no_tracking_file(self, service, git_repo, git_root):
        """Given no tracking file, returns without error."""
        git_repo.get_root.return_value = git_root
        git_repo.get_current_branch.return_value = "feature-branch"

        service.record_commit_intent()  # must not raise

        assert TrackingRepository(git_root, "feature-branch").load() is None

    def test_skips_when_no_git_root(self, service, git_repo):
        """Given no git root, returns without error."""
        git_repo.get_root.return_value = None

        service.record_commit_intent()  # must not raise

    def test_skips_when_no_head_hash(self, service, git_repo, git_root):
        """Given HEAD hash unavailable, leaves pending_inject_head unchanged."""
        git_repo.get_root.return_value = git_root
        git_repo.get_current_branch.return_value = "feature-branch"
        git_repo.get_head_commit_hash.return_value = None

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "existing"
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        service.record_commit_intent()

        loaded = repo.load()
        assert loaded.pending_inject_head == "existing"


class TestProcessCommitClearsPendingFlag:
    """Tests that normal process_commit also clears pending_inject_head."""

    def test_clears_flag_on_successful_normal_inject(self, service, git_repo, git_root):
        """Given normal commit command with pending flag, flag cleared after inject."""
        git_repo.get_root.return_value = git_root
        git_repo.get_head_commit_message.return_value = "Fix bug"

        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "some-old-head"
        tracking.files_tracked = ["file.py"]
        repo = TrackingRepository(git_root, "feature-branch")
        repo.save(tracking)

        git_repo.amend_commit_message.return_value = True

        result = service.process_commit()

        assert result.success
        loaded = repo.load()
        assert loaded.pending_inject_head is None
