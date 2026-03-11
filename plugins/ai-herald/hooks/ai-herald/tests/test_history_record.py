"""Tests for HistoryRecord, HistoryExtensionStats, and HistoryIgnoredStats."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.history_record import HistoryExtensionStats, HistoryIgnoredStats, HistoryRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extension_stats(ai_pct: float = 80.0, ai_lines: int = 60, human_lines: int = 15) -> HistoryExtensionStats:
    return HistoryExtensionStats(ai_percentage=ai_pct, ai_lines=ai_lines, human_lines=human_lines)


def _make_ignored_stats(total: int = 5, added: int = 3, removed: int = 2,
                        patterns: tuple = ('**/generated/**',)) -> HistoryIgnoredStats:
    return HistoryIgnoredStats(
        total_lines=total, lines_added=added, lines_removed=removed, matched_patterns=patterns
    )


def _make_record(**overrides) -> HistoryRecord:
    defaults = dict(
        commit_hash='abc123def456',
        commit_subject='Task 3: implement payment retry logic',
        committed_at='2026-02-10T14:22:00',
        branch='feature/xyz',
        author_email='alice@example.com',
        herald_version='0.0.14',
        files_changed_count=8,
        files_ai_touched_count=6,
        ai_percentage=73.5,
        ai_lines_added=95,
        ai_lines_removed=15,
        human_lines_added=30,
        human_lines_removed=10,
        by_extension={'.py': _make_extension_stats(), '.ts': _make_extension_stats(60.0, 35, 23)},
        ignored=_make_ignored_stats(),
    )
    defaults.update(overrides)
    return HistoryRecord(**defaults)


# ---------------------------------------------------------------------------
# HistoryExtensionStats
# ---------------------------------------------------------------------------

class TestHistoryExtensionStats:
    """Tests for HistoryExtensionStats serialization."""

    def test_to_dict_contains_all_fields(self):
        """Given extension stats, to_dict() returns all three fields."""
        # Given
        stats = _make_extension_stats(ai_pct=80.0, ai_lines=60, human_lines=15)

        # When
        result = stats.to_dict()

        # Then
        assert result == {'ai_percentage': 80.0, 'ai_lines': 60, 'human_lines': 15}

    def test_from_dict_round_trip(self):
        """Given a to_dict() output, from_dict() reconstructs identical stats."""
        # Given
        original = _make_extension_stats(ai_pct=60.0, ai_lines=35, human_lines=23)

        # When
        restored = HistoryExtensionStats.from_dict(original.to_dict())

        # Then
        assert restored == original

    def test_from_dict_coerces_types(self):
        """Given string-typed numeric values, from_dict() coerces to correct types."""
        # Given
        data = {'ai_percentage': '75.5', 'ai_lines': '10', 'human_lines': '5'}

        # When
        stats = HistoryExtensionStats.from_dict(data)

        # Then
        assert stats.ai_percentage == 75.5
        assert stats.ai_lines == 10
        assert stats.human_lines == 5

    def test_from_dict_missing_field_raises(self):
        """Given a dict missing a required field, from_dict() raises KeyError."""
        # Given
        data = {'ai_percentage': 80.0, 'ai_lines': 60}  # missing human_lines

        # When / Then
        with pytest.raises(KeyError):
            HistoryExtensionStats.from_dict(data)


# ---------------------------------------------------------------------------
# HistoryIgnoredStats
# ---------------------------------------------------------------------------

class TestHistoryIgnoredStats:
    """Tests for HistoryIgnoredStats serialization."""

    def test_to_dict_converts_patterns_to_list(self):
        """Given a tuple of patterns, to_dict() converts matched_patterns to list."""
        # Given
        stats = _make_ignored_stats(patterns=('**/generated/**', '**/build/**'))

        # When
        result = stats.to_dict()

        # Then
        assert result['matched_patterns'] == ['**/generated/**', '**/build/**']
        assert isinstance(result['matched_patterns'], list)

    def test_from_dict_converts_patterns_to_tuple(self):
        """Given a list of patterns in dict, from_dict() stores as tuple."""
        # Given
        data = {'total_lines': 5, 'lines_added': 3, 'lines_removed': 2,
                'matched_patterns': ['**/generated/**']}

        # When
        stats = HistoryIgnoredStats.from_dict(data)

        # Then
        assert isinstance(stats.matched_patterns, tuple)
        assert stats.matched_patterns == ('**/generated/**',)

    def test_from_dict_missing_patterns_defaults_to_empty_tuple(self):
        """Given a dict without matched_patterns, from_dict() defaults to empty tuple."""
        # Given
        data = {'total_lines': 0, 'lines_added': 0, 'lines_removed': 0}

        # When
        stats = HistoryIgnoredStats.from_dict(data)

        # Then
        assert stats.matched_patterns == ()

    def test_from_dict_round_trip(self):
        """Given a to_dict() output, from_dict() reconstructs identical stats."""
        # Given
        original = _make_ignored_stats(total=10, added=6, removed=4,
                                       patterns=('**/generated/**', '**/build/**'))

        # When
        restored = HistoryIgnoredStats.from_dict(original.to_dict())

        # Then
        assert restored == original

    def test_empty_returns_zero_valued_instance(self):
        """empty() returns a HistoryIgnoredStats with all zero values."""
        # When
        stats = HistoryIgnoredStats.empty()

        # Then
        assert stats.total_lines == 0
        assert stats.lines_added == 0
        assert stats.lines_removed == 0
        assert stats.matched_patterns == ()

    def test_from_dict_missing_required_field_raises(self):
        """Given a dict missing total_lines, from_dict() raises KeyError."""
        # Given
        data = {'lines_added': 3, 'lines_removed': 2}

        # When / Then
        with pytest.raises(KeyError):
            HistoryIgnoredStats.from_dict(data)


# ---------------------------------------------------------------------------
# HistoryRecord
# ---------------------------------------------------------------------------

class TestHistoryRecordToJsonl:
    """Tests for HistoryRecord.to_jsonl()."""

    def test_to_jsonl_produces_valid_json(self):
        """Given a HistoryRecord, to_jsonl() produces valid JSON."""
        # Given
        record = _make_record()

        # When
        line = record.to_jsonl()

        # Then
        data = json.loads(line)
        assert data['commit_hash'] == 'abc123def456'

    def test_to_jsonl_contains_all_top_level_fields(self):
        """Given a HistoryRecord, to_jsonl() includes all schema fields."""
        # Given
        record = _make_record()

        # When
        data = json.loads(record.to_jsonl())

        # Then
        expected_keys = {
            'commit_hash', 'commit_subject', 'committed_at', 'branch',
            'author_email', 'herald_version', 'files_changed_count',
            'files_ai_touched_count', 'ai_percentage', 'ai_lines_added',
            'ai_lines_removed', 'human_lines_added', 'human_lines_removed',
            'by_extension', 'ignored',
        }
        assert expected_keys == set(data.keys())

    def test_to_jsonl_serializes_by_extension(self):
        """Given extensions in the record, to_jsonl() serializes them correctly."""
        # Given
        record = _make_record(
            by_extension={'.py': HistoryExtensionStats(ai_percentage=80.0, ai_lines=60, human_lines=15)}
        )

        # When
        data = json.loads(record.to_jsonl())

        # Then
        assert '.py' in data['by_extension']
        assert data['by_extension']['.py']['ai_lines'] == 60

    def test_to_jsonl_serializes_ignored(self):
        """Given ignored stats, to_jsonl() serializes matched_patterns as list."""
        # Given
        record = _make_record(ignored=HistoryIgnoredStats(
            total_lines=5, lines_added=3, lines_removed=2,
            matched_patterns=('**/generated/**',)
        ))

        # When
        data = json.loads(record.to_jsonl())

        # Then
        assert data['ignored']['total_lines'] == 5
        assert data['ignored']['matched_patterns'] == ['**/generated/**']

    def test_to_jsonl_produces_single_line(self):
        """Given a HistoryRecord, to_jsonl() produces output with no newlines."""
        # Given
        record = _make_record()

        # When
        line = record.to_jsonl()

        # Then
        assert '\n' not in line


class TestHistoryRecordFromJsonl:
    """Tests for HistoryRecord.from_jsonl()."""

    def test_from_jsonl_round_trip(self):
        """Given a to_jsonl() output, from_jsonl() reconstructs identical record."""
        # Given
        original = _make_record()

        # When
        restored = HistoryRecord.from_jsonl(original.to_jsonl())

        # Then
        assert restored.commit_hash == original.commit_hash
        assert restored.ai_percentage == original.ai_percentage
        assert restored.by_extension['.py'].ai_lines == original.by_extension['.py'].ai_lines
        assert restored.ignored.total_lines == original.ignored.total_lines
        assert restored.ignored.matched_patterns == original.ignored.matched_patterns

    def test_from_jsonl_handles_missing_ignored_field(self):
        """Given a JSONL line without 'ignored', from_jsonl() defaults to zeros."""
        # Given
        data = json.loads(_make_record().to_jsonl())
        del data['ignored']
        line = json.dumps(data)

        # When
        record = HistoryRecord.from_jsonl(line)

        # Then
        assert record.ignored.total_lines == 0
        assert record.ignored.matched_patterns == ()

    def test_from_jsonl_handles_missing_by_extension_field(self):
        """Given a JSONL line without 'by_extension', from_jsonl() defaults to empty dict."""
        # Given
        data = json.loads(_make_record().to_jsonl())
        del data['by_extension']
        line = json.dumps(data)

        # When
        record = HistoryRecord.from_jsonl(line)

        # Then
        assert record.by_extension == {}

    def test_from_jsonl_malformed_json_raises(self):
        """Given an invalid JSON string, from_jsonl() raises JSONDecodeError."""
        # When / Then
        with pytest.raises(json.JSONDecodeError):
            HistoryRecord.from_jsonl('not valid json {{{')

    def test_from_jsonl_missing_required_field_raises(self):
        """Given a JSONL line missing commit_hash, from_jsonl() raises KeyError."""
        # Given
        data = json.loads(_make_record().to_jsonl())
        del data['commit_hash']
        line = json.dumps(data)

        # When / Then
        with pytest.raises(KeyError):
            HistoryRecord.from_jsonl(line)

    def test_from_jsonl_handles_whitespace_padding(self):
        """Given a line with leading/trailing whitespace, from_jsonl() parses it."""
        # Given
        line = '  ' + _make_record().to_jsonl() + '\n'

        # When
        record = HistoryRecord.from_jsonl(line)

        # Then
        assert record.commit_hash == 'abc123def456'

    @pytest.mark.parametrize('ai_percentage,ai_lines_added', [
        (0.0, 0),
        (100.0, 200),
        (50.5, 50),
    ])
    def test_from_jsonl_numeric_field_values(self, ai_percentage: float, ai_lines_added: int):
        """Given various numeric field values, from_jsonl() preserves them correctly."""
        # Given
        record = _make_record(ai_percentage=ai_percentage, ai_lines_added=ai_lines_added)
        line = record.to_jsonl()

        # When
        restored = HistoryRecord.from_jsonl(line)

        # Then
        assert restored.ai_percentage == ai_percentage
        assert restored.ai_lines_added == ai_lines_added
