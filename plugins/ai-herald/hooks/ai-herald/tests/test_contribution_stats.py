"""Tests for ContributionStats."""

import sys
from pathlib import Path
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import (
    CodeGenStats,
    ContributionStats,
    ContributorStats,
    FileTypeStats,
    LineStats,
)


def _make_stats(ai_pct: float) -> ContributionStats:
    """Helper to create ContributionStats with given AI total percentage."""
    ai = ContributorStats(
        total=LineStats(lines=10, percentage=ai_pct),
        added=LineStats(lines=10, percentage=ai_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    human_pct = 100.0 - ai_pct if ai_pct <= 100.0 else 0.0
    human = ContributorStats(
        total=LineStats(lines=5, percentage=human_pct),
        added=LineStats(lines=5, percentage=human_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    return ContributionStats(ai_stats=ai, human_stats=human, by_file_type={})


@pytest.mark.parametrize(
    "ai_percentage, expected",
    [
        (0.0, "[AI: 0%]"),
        (50.0, "[AI: 50%]"),
        (100.0, "[AI: 100%]"),
        (85.4, "[AI: 85%]"),
        (85.5, "[AI: 86%]"),
        (99.5, "[AI: 100%]"),
        (0.4, "[AI: 0%]"),
        (33.3, "[AI: 33%]"),
    ],
)
def test_format_compact(ai_percentage: float, expected: str):
    """Given various AI percentages, format_compact returns [AI: X%] with proper rounding."""
    # Given
    stats = _make_stats(ai_percentage)

    # When
    result = stats.format_compact()

    # Then
    assert result == expected


def test_from_dict_round_trip():
    """Given a stats dict from to_dict(), from_dict() reconstructs the same stats."""
    # Given
    original = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=42, percentage=84.0),
            added=LineStats(lines=40, percentage=90.0),
            removed=LineStats(lines=2, percentage=50.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=8, percentage=16.0),
            added=LineStats(lines=4, percentage=10.0),
            removed=LineStats(lines=2, percentage=50.0),
        ),
        by_file_type={
            '.py': FileTypeStats(ai_lines=30, human_lines=5, total_lines=35,
                                 ai_percentage=85.7, file_count=2),
        },
    )

    # When
    data = original.to_dict()
    restored = ContributionStats.from_dict(data)

    # Then
    assert restored.ai_lines == 42
    assert restored.ai_percentage == 84.0
    assert restored.human_lines == 8
    assert restored.format_compact() == "[AI: 84%]"
    assert '.py' in restored.by_file_type
    assert restored.by_file_type['.py'].file_count == 2


def test_from_dict_empty_stats():
    """Given a minimal stats dict, from_dict() handles missing fields."""
    # Given
    data = {
        'ai': {
            'total': {'lines': 0, 'percentage': 0.0},
            'added': {'lines': 0, 'percentage': 0.0},
            'removed': {'lines': 0, 'percentage': 0.0},
        },
        'human': {
            'total': {'lines': 0, 'percentage': 0.0},
            'added': {'lines': 0, 'percentage': 0.0},
            'removed': {'lines': 0, 'percentage': 0.0},
        },
    }

    # When
    stats = ContributionStats.from_dict(data)

    # Then
    assert stats.ai_lines == 0
    assert stats.format_compact() == "[AI: 0%]"


def test_format_description():
    """Given stats, format_description() returns markdown with heading and code fence."""
    # Given
    stats = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=170, percentage=85.0),
            added=LineStats(lines=140, percentage=93.3),
            removed=LineStats(lines=30, percentage=60.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=30, percentage=15.0),
            added=LineStats(lines=10, percentage=6.7),
            removed=LineStats(lines=20, percentage=40.0),
        ),
        by_file_type={},
    )

    # When
    result = stats.format_description()

    # Then
    assert result.startswith("## AI Contribution Stats\n\n```\n")
    assert result.endswith("```")
    assert "Overall: +150 -50" in result
    assert "AI: 170 lines (85.0%)" in result
    assert "Human: 30 lines (15.0%)" in result


def test_format_message_with_tracked_extensions():
    """Given stats with multiple extensions, format_message includes tracked list."""
    # Given
    stats = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=100, percentage=80.0),
            added=LineStats(lines=100, percentage=80.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=25, percentage=20.0),
            added=LineStats(lines=25, percentage=20.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        by_file_type={
            '.py': FileTypeStats(ai_lines=50, human_lines=10, total_lines=60,
                                ai_percentage=83.3, file_count=2),
            '.java': FileTypeStats(ai_lines=30, human_lines=10, total_lines=40,
                                  ai_percentage=75.0, file_count=1),
            '.kt': FileTypeStats(ai_lines=20, human_lines=5, total_lines=25,
                                ai_percentage=80.0, file_count=1),
        },
    )

    # When
    result = stats.format_message()

    # Then
    assert "Tracked: .java, .kt, .py" in result
    # Verify alphabetical order
    java_pos = result.index(".java")
    kt_pos = result.index(".kt")
    py_pos = result.index(".py")
    assert java_pos < kt_pos < py_pos


def test_format_message_without_tracked_extensions():
    """Given stats with no extensions, format_message omits tracked line."""
    # Given
    stats = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=100, percentage=100.0),
            added=LineStats(lines=100, percentage=100.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=0, percentage=0.0),
            added=LineStats(lines=0, percentage=0.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        by_file_type={},
    )

    # When
    result = stats.format_message()

    # Then
    assert "Tracked:" not in result
    assert "Overall: +100 -0" in result


def test_format_message_filters_zero_line_extensions():
    """Given extensions with zero changes, format_message excludes them."""
    # Given
    stats = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=50, percentage=100.0),
            added=LineStats(lines=50, percentage=100.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=0, percentage=0.0),
            added=LineStats(lines=0, percentage=0.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        by_file_type={
            '.py': FileTypeStats(ai_lines=50, human_lines=0, total_lines=50,
                                ai_percentage=100.0, file_count=1),
            '.java': FileTypeStats(ai_lines=0, human_lines=0, total_lines=0,
                                  ai_percentage=0.0, file_count=0),
        },
    )

    # When
    result = stats.format_message()

    # Then
    assert "Tracked: .py" in result
    assert ".java" not in result


def test_format_message_tracked_extensions_sorted():
    """Given multiple extensions, they are sorted alphabetically."""
    # Given
    stats = ContributionStats(
        ai_stats=ContributorStats(
            total=LineStats(lines=100, percentage=100.0),
            added=LineStats(lines=100, percentage=100.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        human_stats=ContributorStats(
            total=LineStats(lines=0, percentage=0.0),
            added=LineStats(lines=0, percentage=0.0),
            removed=LineStats(lines=0, percentage=0.0),
        ),
        by_file_type={
            '.yml': FileTypeStats(ai_lines=10, human_lines=0, total_lines=10,
                                 ai_percentage=100.0, file_count=1),
            '.kt': FileTypeStats(ai_lines=30, human_lines=0, total_lines=30,
                                ai_percentage=100.0, file_count=1),
            '.java': FileTypeStats(ai_lines=50, human_lines=0, total_lines=50,
                                  ai_percentage=100.0, file_count=2),
            '.py': FileTypeStats(ai_lines=10, human_lines=0, total_lines=10,
                                ai_percentage=100.0, file_count=1),
        },
    )

    # When
    result = stats.format_message()

    # Then
    assert "Tracked: .java, .kt, .py, .yml" in result
    # Verify order despite dict insertion order
    assert result.index(".java") < result.index(".kt")
    assert result.index(".kt") < result.index(".py")
    assert result.index(".py") < result.index(".yml")


# ---------------------------------------------------------------------------
# CodeGenStats tests
# ---------------------------------------------------------------------------

class TestCodeGenStatsDefault:
    """Tests for default code_generated field in ContributionStats."""

    def _make_contribution_stats(self, **kwargs) -> ContributionStats:
        ai = ContributorStats(
            total=LineStats(lines=10, percentage=100.0),
            added=LineStats(lines=10, percentage=100.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        human = ContributorStats(
            total=LineStats(lines=0, percentage=0.0),
            added=LineStats(lines=0, percentage=0.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        return ContributionStats(ai_stats=ai, human_stats=human, by_file_type={}, **kwargs)

    def test_code_generated_defaults_to_zeros(self):
        """Given no code_generated arg, code_generated has all zeros."""
        stats = self._make_contribution_stats()
        assert stats.code_generated.total == 0
        assert stats.code_generated.added == 0
        assert stats.code_generated.removed == 0
        assert stats.code_generated.matched_patterns == frozenset()

    def test_code_generated_stores_given_stats(self):
        """Given code_generated arg, property returns it."""
        cg = CodeGenStats(total=50, added=30, removed=20, matched_patterns=frozenset({"**/generated/**"}))
        stats = self._make_contribution_stats(code_generated=cg)
        assert stats.code_generated.total == 50
        assert stats.code_generated.added == 30
        assert stats.code_generated.removed == 20
        assert "**/generated/**" in stats.code_generated.matched_patterns


class TestFormatMessageCodeGen:
    """Tests for format_message() with code-gen section."""

    def _make_stats(self, cg: CodeGenStats) -> ContributionStats:
        ai = ContributorStats(
            total=LineStats(lines=80, percentage=80.0),
            added=LineStats(lines=80, percentage=80.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        human = ContributorStats(
            total=LineStats(lines=20, percentage=20.0),
            added=LineStats(lines=20, percentage=20.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        return ContributionStats(ai_stats=ai, human_stats=human, by_file_type={}, code_generated=cg)

    def test_format_message_omits_code_gen_section_when_zero(self):
        """Given zero code-gen lines, format_message omits the Code-Gen section."""
        cg = CodeGenStats(total=0, added=0, removed=0, matched_patterns=frozenset())
        stats = self._make_stats(cg)
        assert "Code-Gen" not in stats.format_message()

    def test_format_message_includes_code_gen_section_when_nonzero(self):
        """Given nonzero code-gen lines, format_message appends Code-Gen section."""
        cg = CodeGenStats(total=50, added=30, removed=20, matched_patterns=frozenset({"**/generated/**"}))
        stats = self._make_stats(cg)
        msg = stats.format_message()
        assert "Code-Gen: 50 lines excluded" in msg
        assert "+30 -20" in msg
        assert "Matched patterns: **/generated/**" in msg

    def test_format_message_code_gen_patterns_sorted(self):
        """Given multiple matched patterns, they appear sorted in format_message."""
        cg = CodeGenStats(
            total=50, added=50, removed=0,
            matched_patterns=frozenset({"**/generated/**", "**/build/generated/**"})
        )
        stats = self._make_stats(cg)
        msg = stats.format_message()
        # Both patterns present, sorted alphabetically
        assert "**/build/generated/**, **/generated/**" in msg


class TestToAndFromDictWithCodeGen:
    """Tests for to_dict / from_dict round-trip with code_generated."""

    def test_to_dict_includes_code_generated(self):
        """Given ContributionStats with code_generated, to_dict() includes it."""
        cg = CodeGenStats(total=40, added=25, removed=15, matched_patterns=frozenset({"**/generated/**"}))
        ai = ContributorStats(
            total=LineStats(lines=60, percentage=60.0),
            added=LineStats(lines=60, percentage=60.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        human = ContributorStats(
            total=LineStats(lines=40, percentage=40.0),
            added=LineStats(lines=40, percentage=40.0),
            removed=LineStats(lines=0, percentage=0.0),
        )
        stats = ContributionStats(ai_stats=ai, human_stats=human, by_file_type={}, code_generated=cg)
        d = stats.to_dict()

        assert d['code_generated']['total'] == 40
        assert d['code_generated']['added'] == 25
        assert d['code_generated']['removed'] == 15
        assert d['code_generated']['matched_patterns'] == ["**/generated/**"]

    def test_from_dict_restores_code_generated(self):
        """Given dict with code_generated, from_dict() restores it."""
        data = {
            'ai': {
                'total': {'lines': 60, 'percentage': 60.0},
                'added': {'lines': 60, 'percentage': 60.0},
                'removed': {'lines': 0, 'percentage': 0.0},
            },
            'human': {
                'total': {'lines': 40, 'percentage': 40.0},
                'added': {'lines': 40, 'percentage': 40.0},
                'removed': {'lines': 0, 'percentage': 0.0},
            },
            'code_generated': {
                'total': 40,
                'added': 25,
                'removed': 15,
                'matched_patterns': ["**/generated/**"],
            },
        }
        stats = ContributionStats.from_dict(data)
        assert stats.code_generated.total == 40
        assert stats.code_generated.added == 25
        assert "**/generated/**" in stats.code_generated.matched_patterns

    def test_from_dict_missing_code_generated_defaults_to_zeros(self):
        """Given dict without code_generated, from_dict() defaults to zeros."""
        data = {
            'ai': {
                'total': {'lines': 10, 'percentage': 100.0},
                'added': {'lines': 10, 'percentage': 100.0},
                'removed': {'lines': 0, 'percentage': 0.0},
            },
            'human': {
                'total': {'lines': 0, 'percentage': 0.0},
                'added': {'lines': 0, 'percentage': 0.0},
                'removed': {'lines': 0, 'percentage': 0.0},
            },
        }
        stats = ContributionStats.from_dict(data)
        assert stats.code_generated.total == 0
        assert stats.code_generated.matched_patterns == frozenset()
