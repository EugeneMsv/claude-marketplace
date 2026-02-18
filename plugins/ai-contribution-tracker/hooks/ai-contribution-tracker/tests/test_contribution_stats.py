"""Tests for ContributionStats."""

import sys
from pathlib import Path
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import (
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
