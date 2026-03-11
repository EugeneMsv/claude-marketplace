"""Tests for HistoryQueryService."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.history_record import HistoryExtensionStats, HistoryIgnoredStats, HistoryRecord
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.history_repository import HistoryRepository
from services.query.history_query_service import (
    HistoryQueryService,
    _parse_since,
    _period_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(history_enabled: bool = True) -> Configuration:
    return Configuration(
        enabled=True,
        base_branches=["main"],
        tracked_extensions={".py"},
        enable_logging=False,
        log_file="test.log",
        history_enabled=history_enabled,
    )


def _make_record(
    commit_hash: str = 'abc123',
    committed_at: str = '2026-02-10T14:00:00+00:00',
    branch: str = 'feature/xyz',
    author_email: str = 'alice@example.com',
    ai_percentage: float = 75.0,
    ai_lines_added: int = 90,
    ai_lines_removed: int = 10,
    human_lines_added: int = 30,
    human_lines_removed: int = 5,
    ignored_total: int = 0,
    ignored_patterns: tuple = (),
) -> HistoryRecord:
    return HistoryRecord(
        commit_hash=commit_hash,
        commit_subject='Task 1: add feature',
        committed_at=committed_at,
        branch=branch,
        author_email=author_email,
        herald_version='0.0.14',
        files_changed_count=3,
        files_ai_touched_count=2,
        ai_percentage=ai_percentage,
        ai_lines_added=ai_lines_added,
        ai_lines_removed=ai_lines_removed,
        human_lines_added=human_lines_added,
        human_lines_removed=human_lines_removed,
        by_extension={'.py': HistoryExtensionStats(ai_percentage=80.0, ai_lines=60, human_lines=15)},
        ignored=HistoryIgnoredStats(
            total_lines=ignored_total,
            lines_added=ignored_total,
            lines_removed=0,
            matched_patterns=ignored_patterns,
        ),
    )


def _make_repo_with_records(records: list, tmpdir: Path) -> HistoryRepository:
    """Build a HistoryRepository backed by a temp dir and pre-populate it."""
    mock_git = MagicMock(spec=GitRepository)
    mock_git.get_remote_url.return_value = 'git@github.com:alice/my-repo.git'
    mock_git.get_root.return_value = tmpdir

    with patch.object(HistoryRepository, '_GLOBAL_DIR', tmpdir):
        repo = HistoryRepository(mock_git)
        for r in records:
            repo.append(r)
    return repo


# ---------------------------------------------------------------------------
# _parse_since
# ---------------------------------------------------------------------------

class TestParseSince:

    def test_days_shorthand(self):
        """'30d' parses to now minus 30 days."""
        from datetime import datetime, timezone, timedelta
        result = _parse_since('30d')
        expected = datetime.now(tz=timezone.utc) - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 5

    def test_weeks_shorthand(self):
        """'2w' parses to now minus 14 days."""
        from datetime import datetime, timezone, timedelta
        result = _parse_since('2w')
        expected = datetime.now(tz=timezone.utc) - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 5

    def test_months_shorthand(self):
        """'1m' parses to now minus 30 days."""
        from datetime import datetime, timezone, timedelta
        result = _parse_since('1m')
        expected = datetime.now(tz=timezone.utc) - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 5

    def test_iso_date(self):
        """'2026-01-01' parses to datetime(2026, 1, 1)."""
        result = _parse_since('2026-01-01')
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1

    def test_invalid_returns_none(self):
        """Unrecognised string returns None."""
        assert _parse_since('invalid') is None


# ---------------------------------------------------------------------------
# Empty / disabled guards
# ---------------------------------------------------------------------------

class TestDisabledAndEmptyGuards:

    def test_disabled_with_no_file_returns_disabled_message(self):
        """Given history disabled and no file, returns disabled message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_git = MagicMock(spec=GitRepository)
            mock_git.get_remote_url.return_value = 'git@github.com:alice/repo.git'
            mock_git.get_root.return_value = Path(tmpdir)

            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)
                service = HistoryQueryService(repo, _make_config(history_enabled=False))
                result = service.query()

        assert "not enabled" in result.lower() or "disabled" in result.lower()

    def test_enabled_with_no_records_returns_no_records_message(self):
        """Given history enabled but empty file, returns no-records message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query()

        assert "no history records" in result.lower()

    def test_filters_return_no_match_message(self):
        """Given filters that match nothing, returns no-match message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            records = [_make_record(author_email='alice@example.com')]
            repo = _make_repo_with_records(records, Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(author='nobody@example.com')

        assert "no records match" in result.lower()


# ---------------------------------------------------------------------------
# Weekly grouping
# ---------------------------------------------------------------------------

class TestWeeklyGrouping:

    def test_two_commits_same_week_grouped_together(self):
        """Given two commits in the same ISO week, they form one group."""
        # Both on Mon 2026-01-12 and Wed 2026-01-14 → same week (starts 2026-01-12)
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00', branch='feature/a')
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-14T10:00:00+00:00', branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['commits'] == 2

    def test_commits_in_different_weeks_form_separate_groups(self):
        """Given commits in different weeks, each forms its own group."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00', branch='feature/a')
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-19T10:00:00+00:00', branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 2

    def test_weekly_period_key_is_monday(self):
        """Weekly period key is the Monday of the commit's week."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-14T10:00:00+00:00')  # Wednesday

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert data[0]['period'] == '2026-01-12'  # Monday of that week


# ---------------------------------------------------------------------------
# Monthly grouping
# ---------------------------------------------------------------------------

class TestMonthlyGrouping:

    def test_commits_in_same_month_grouped_together(self):
        """Given two commits in Jan 2026, they form one group."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-05T10:00:00+00:00', branch='feature/a')
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-25T10:00:00+00:00', branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='month', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['commits'] == 2
        assert data[0]['period'] == '2026-01'

    def test_commits_in_different_months_form_separate_groups(self):
        """Given commits in Jan and Feb, they form two groups."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-15T10:00:00+00:00', branch='feature/a')
        r2 = _make_record(commit_hash='h2', committed_at='2026-02-10T10:00:00+00:00', branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='month', output_format='json')

        data = json.loads(result)
        assert len(data) == 2
        periods = [d['period'] for d in data]
        assert '2026-01' in periods
        assert '2026-02' in periods


# ---------------------------------------------------------------------------
# Commit grouping
# ---------------------------------------------------------------------------

class TestCommitGrouping:

    def test_each_commit_forms_own_group(self):
        """Given 3 commits, --by commit produces 3 groups."""
        records = [
            _make_record(commit_hash=f'h{i}', committed_at=f'2026-01-0{i+1}T10:00:00+00:00', branch=f'feature/{i}')
            for i in range(3)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records(records, Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='commit', output_format='json')

        data = json.loads(result)
        assert len(data) == 3
        for d in data:
            assert d['commits'] == 1


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestFilters:

    def test_since_filter_excludes_old_records(self):
        """Given --since 7d, records older than 7 days are excluded."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        recent = (now - timedelta(days=3)).isoformat()
        old = (now - timedelta(days=30)).isoformat()

        r_recent = _make_record(commit_hash='recent', committed_at=recent)
        r_old = _make_record(commit_hash='old', committed_at=old)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r_recent, r_old], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(since='7d', output_format='json')

        data = json.loads(result)
        hashes = [d['period'] for d in data]
        # Only the recent record should appear (by commit grouping would show 'recent')
        # But we're using default 'week' grouping, so just check total commits
        total = sum(d['commits'] for d in data)
        assert total == 1

    def test_author_filter_includes_only_matching_author(self):
        """Given --author, only records from that author are included."""
        r_alice = _make_record(commit_hash='h1', author_email='alice@example.com',
                               committed_at='2026-01-10T10:00:00+00:00', branch='feature/alice')
        r_bob = _make_record(commit_hash='h2', author_email='bob@example.com',
                             committed_at='2026-01-11T10:00:00+00:00', branch='feature/bob')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r_alice, r_bob], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(author='alice@example.com', output_format='json')

        data = json.loads(result)
        total = sum(d['commits'] for d in data)
        assert total == 1

    def test_author_filter_no_match_returns_message(self):
        """Given --author with no match, returns no-match message."""
        r = _make_record(commit_hash='h1', author_email='alice@example.com')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(author='nobody@example.com')

        assert "no records match" in result.lower()


# ---------------------------------------------------------------------------
# Aggregation correctness
# ---------------------------------------------------------------------------

class TestAggregation:

    def test_line_counts_summed_across_commits(self):
        """Given two commits in the same week, line counts are summed."""
        r1 = _make_record(
            commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00', branch='feature/a',
            ai_lines_added=50, human_lines_added=10,
            ai_lines_removed=5, human_lines_removed=2,
        )
        r2 = _make_record(
            commit_hash='h2', committed_at='2026-01-13T10:00:00+00:00', branch='feature/b',
            ai_lines_added=30, human_lines_added=20,
            ai_lines_removed=3, human_lines_removed=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['ai_lines_added'] == 80
        assert data[0]['human_lines_added'] == 30
        assert data[0]['ai_lines_removed'] == 8
        assert data[0]['human_lines_removed'] == 3

    def test_ignored_lines_summed(self):
        """Given commits with ignored lines, totals are summed."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00', branch='feature/a',
                          ignored_total=5, ignored_patterns=('**/generated/**',))
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-13T10:00:00+00:00', branch='feature/b',
                          ignored_total=3, ignored_patterns=('**/generated/**',))

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert data[0]['ignored_lines'] == 8
        assert data[0]['ignored_patterns'] == ['**/generated/**']


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------

class TestOutputFormats:

    def test_json_output_is_valid_json_array(self):
        """JSON output is a valid JSON array."""
        r = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='json')

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_json_output_has_required_fields(self):
        """JSON output includes all required fields."""
        r = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='json')

        g = json.loads(result)[0]
        required = [
            'period', 'commits', 'ai_percentage',
            'ai_lines_added', 'human_lines_added',
            'ai_lines_removed', 'human_lines_removed',
            'ignored_lines', 'ignored_patterns',
        ]
        for field in required:
            assert field in g, f"Missing field: {field}"

    def test_csv_output_has_header_row(self):
        """CSV output starts with a header row."""
        r = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='csv')

        lines = result.strip().splitlines()
        assert lines[0].startswith('period,commits')

    def test_table_output_contains_identity(self):
        """Table output contains the repo identity string."""
        r = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='table')

        assert repo.repo_identity in result

    def test_table_output_contains_ai_percentage(self):
        """Table output contains the AI percentage."""
        r = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00',
                         ai_percentage=88.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='table')

        assert '88%' in result

    def test_table_output_contains_trend_footer(self):
        """Table output contains the trend/footer line."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00', branch='feature/a')
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-19T10:00:00+00:00', branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(output_format='table')

        assert 'Trend:' in result
        assert 'Total:' in result
        assert 'Avg AI%:' in result


# ---------------------------------------------------------------------------
# Branch deduplication
# ---------------------------------------------------------------------------

class TestBranchDeduplication:

    def test_same_branch_multiple_commits_deduped_to_one(self):
        """Given 3 commits on the same branch, only the latest survives → 1 group."""
        r1 = _make_record(commit_hash='h1', committed_at='2026-01-10T10:00:00+00:00',
                          branch='feature/xyz', ai_percentage=50.0)
        r2 = _make_record(commit_hash='h2', committed_at='2026-01-12T10:00:00+00:00',
                          branch='feature/xyz', ai_percentage=70.0)
        r3 = _make_record(commit_hash='h3', committed_at='2026-01-14T10:00:00+00:00',
                          branch='feature/xyz', ai_percentage=90.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r1, r2, r3], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['commits'] == 1

    def test_latest_commit_stats_are_used_not_earliest(self):
        """Given two commits on same branch, the later commit's stats are used."""
        r_early = _make_record(commit_hash='h1', committed_at='2026-01-10T10:00:00+00:00',
                               branch='feature/xyz', ai_percentage=50.0)
        r_late = _make_record(commit_hash='h2', committed_at='2026-01-14T10:00:00+00:00',
                              branch='feature/xyz', ai_percentage=90.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r_early, r_late], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['ai_percentage'] == 90.0

    def test_different_branches_not_deduplicated(self):
        """Given two commits on different branches, both survive dedup."""
        r_a = _make_record(commit_hash='h1', committed_at='2026-01-12T10:00:00+00:00',
                           branch='feature/a')
        r_b = _make_record(commit_hash='h2', committed_at='2026-01-14T10:00:00+00:00',
                           branch='feature/b')

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r_a, r_b], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(by='week', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['commits'] == 2

    def test_dedup_applies_within_since_filter_window(self):
        """Given two commits on same branch, dedup keeps the latest within the since window."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        early = (now - timedelta(days=10)).isoformat()
        late = (now - timedelta(days=3)).isoformat()

        r_early = _make_record(commit_hash='h1', committed_at=early,
                               branch='feature/xyz', ai_percentage=40.0)
        r_late = _make_record(commit_hash='h2', committed_at=late,
                              branch='feature/xyz', ai_percentage=80.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _make_repo_with_records([r_early, r_late], Path(tmpdir))
            service = HistoryQueryService(repo, _make_config())
            result = service.query(since='7d', output_format='json')

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]['commits'] == 1
        assert data[0]['ai_percentage'] == 80.0
