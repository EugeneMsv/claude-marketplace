"""Tests for HistoryAppendService."""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import (
    ContributionStats, ContributorStats, FileTypeStats, IgnoredFilesStats, LineStats
)
from domain.tracking_data import TrackingData
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.history_repository import HistoryRepository
from services.history_append_service import HistoryAppendService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logger():
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    return logger


def _make_config(history_enabled: bool = True) -> Configuration:
    return Configuration(
        enabled=True,
        base_branches=["main"],
        tracked_extensions={".py"},
        enable_logging=False,
        log_file="test.log",
        history_enabled=history_enabled,
    )


def _make_stats(ai_pct: float = 75.0, by_file_type=None, ignored=None) -> ContributionStats:
    ai = ContributorStats(
        total=LineStats(lines=90, percentage=ai_pct),
        added=LineStats(lines=90, percentage=ai_pct),
        removed=LineStats(lines=10, percentage=ai_pct),
    )
    human = ContributorStats(
        total=LineStats(lines=30, percentage=100.0 - ai_pct),
        added=LineStats(lines=30, percentage=100.0 - ai_pct),
        removed=LineStats(lines=5, percentage=100.0 - ai_pct),
    )
    return ContributionStats(
        ai_stats=ai,
        human_stats=human,
        by_file_type=by_file_type or {},
        ignored_files=ignored,
    )


def _make_tracking(branch: str = "feature/xyz", merge_base: str = "base123") -> TrackingData:
    t = TrackingData(branch)
    t.merge_base = merge_base
    t.files_tracked = ["a.py", "b.py", "c.py"]
    return t


def _make_git_repo() -> MagicMock:
    mock = MagicMock(spec=GitRepository)
    mock.get_head_commit_hash.return_value = "abc123def456"
    mock.get_head_commit_subject.return_value = "Task 1: add feature"
    mock.get_head_commit_timestamp.return_value = "2026-02-10T14:22:00+00:00"
    mock.get_author_email.return_value = "alice@example.com"
    mock.get_changed_file_count.return_value = 3
    return mock


# ---------------------------------------------------------------------------
# Feature flag guard
# ---------------------------------------------------------------------------

class TestHistoryDisabled:

    def test_no_op_when_history_disabled(self):
        """Given history_enabled=False, append_commit does nothing."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        config = _make_config(history_enabled=False)

        service = HistoryAppendService(git_repo, history_repo, config, _make_logger())
        service.append_commit(_make_stats(), _make_tracking())

        history_repo.append.assert_not_called()
        git_repo.get_head_commit_hash.assert_not_called()


# ---------------------------------------------------------------------------
# Successful append
# ---------------------------------------------------------------------------

class TestSuccessfulAppend:

    def test_appends_record_when_enabled(self):
        """Given history enabled, append_commit calls history_repo.append."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())

        history_repo.append.assert_called_once()

    def test_record_has_correct_commit_hash(self):
        """Given HEAD hash, record.commit_hash matches."""
        git_repo = _make_git_repo()
        git_repo.get_head_commit_hash.return_value = "deadbeef1234"
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert record.commit_hash == "deadbeef1234"

    def test_record_has_correct_branch(self):
        """Given tracking with branch, record.branch matches."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking(branch="feature/auth"))

        record = history_repo.append.call_args[0][0]
        assert record.branch == "feature/auth"

    def test_record_has_correct_ai_percentage(self):
        """Given stats with ai_percentage=80, record.ai_percentage matches."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(ai_pct=80.0), _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert record.ai_percentage == 80.0

    def test_record_files_ai_touched_count(self):
        """Given 3 files_tracked, record.files_ai_touched_count == 3."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        tracking = _make_tracking()
        tracking.files_tracked = ["a.py", "b.py", "c.py"]
        service.append_commit(_make_stats(), tracking)

        record = history_repo.append.call_args[0][0]
        assert record.files_ai_touched_count == 3

    def test_record_files_changed_count_from_git(self):
        """Given git returns 5 changed files, record.files_changed_count == 5."""
        git_repo = _make_git_repo()
        git_repo.get_changed_file_count.return_value = 5
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert record.files_changed_count == 5

    def test_get_changed_file_count_called_with_merge_base(self):
        """Given tracking.merge_base='base123', get_changed_file_count called with it."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking(merge_base="base123"))

        git_repo.get_changed_file_count.assert_called_once_with("base123")


# ---------------------------------------------------------------------------
# by_extension mapping
# ---------------------------------------------------------------------------

class TestByExtensionMapping:

    def test_by_extension_maps_file_type_stats(self):
        """Given FileTypeStats for .py, record.by_extension['.py'] has correct fields."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        ft = FileTypeStats(ai_lines=60, human_lines=15, total_lines=75, ai_percentage=80.0, file_count=2)
        stats = _make_stats(by_file_type={".py": ft})

        service.append_commit(stats, _make_tracking())

        record = history_repo.append.call_args[0][0]
        ext_stats = record.by_extension[".py"]
        assert ext_stats.ai_percentage == 80.0
        assert ext_stats.ai_lines == 60
        assert ext_stats.human_lines == 15

    def test_by_extension_empty_when_no_file_types(self):
        """Given no by_file_type, record.by_extension is empty."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(by_file_type={}), _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert record.by_extension == {}


# ---------------------------------------------------------------------------
# ignored mapping
# ---------------------------------------------------------------------------

class TestIgnoredMapping:

    def test_ignored_fields_mapped_correctly(self):
        """Given IgnoredFilesStats, record.ignored has correct field mapping."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        ig = IgnoredFilesStats(
            total=5, added=3, removed=2,
            matched_patterns=frozenset(["**/generated/**", "**/vendor/**"])
        )
        stats = _make_stats(ignored=ig)

        service.append_commit(stats, _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert record.ignored.total_lines == 5
        assert record.ignored.lines_added == 3
        assert record.ignored.lines_removed == 2
        assert set(record.ignored.matched_patterns) == {"**/generated/**", "**/vendor/**"}

    def test_ignored_matched_patterns_is_sorted_tuple(self):
        """Given matched_patterns frozenset, record.ignored.matched_patterns is sorted tuple."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        ig = IgnoredFilesStats(
            total=2, added=1, removed=1,
            matched_patterns=frozenset(["**/z/**", "**/a/**"])
        )
        stats = _make_stats(ignored=ig)

        service.append_commit(stats, _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert isinstance(record.ignored.matched_patterns, tuple)
        assert record.ignored.matched_patterns == ("**/a/**", "**/z/**")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_skips_when_no_commit_hash(self):
        """Given get_head_commit_hash returns None, does not append."""
        git_repo = _make_git_repo()
        git_repo.get_head_commit_hash.return_value = None
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())

        history_repo.append.assert_not_called()

    def test_does_not_raise_when_history_repo_raises(self):
        """Given history_repo.append raises, append_commit does not propagate the error."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        history_repo.append.side_effect = IOError("disk full")
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())  # must not raise

    def test_no_merge_base_uses_zero_for_files_changed(self):
        """Given tracking.merge_base=None, files_changed_count defaults to 0."""
        git_repo = _make_git_repo()
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        tracking = _make_tracking()
        tracking.merge_base = None

        service.append_commit(_make_stats(), tracking)

        record = history_repo.append.call_args[0][0]
        assert record.files_changed_count == 0
        git_repo.get_changed_file_count.assert_not_called()

    def test_fallback_timestamp_used_when_git_returns_none(self):
        """Given get_head_commit_timestamp returns None, committed_at is still a string."""
        git_repo = _make_git_repo()
        git_repo.get_head_commit_timestamp.return_value = None
        history_repo = MagicMock(spec=HistoryRepository)
        service = HistoryAppendService(git_repo, history_repo, _make_config(), _make_logger())

        service.append_commit(_make_stats(), _make_tracking())

        record = history_repo.append.call_args[0][0]
        assert isinstance(record.committed_at, str)
        assert len(record.committed_at) > 0
