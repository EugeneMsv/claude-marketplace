"""Tests for StatsCalculator."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.stats_calculator import StatsCalculator
from domain.tracking_data import TrackingData
from domain.diff import Diff, DiffFile
from domain.line_hasher import LineHasher


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def calculator(hasher):
    return StatsCalculator(hasher)


@pytest.fixture
def tracking():
    return TrackingData("test-branch")


class TestCountFileLines:
    """Tests for _count_file_lines method (added lines attribution)."""

    def test_all_lines_ai(self, calculator, tracking, hasher):
        """Given all lines tracked as AI, counts all as AI."""
        tracking.add_ai_lines("file.py", ["line A", "line B"], hasher)
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line B"],
            tracking
        )

        assert ai_count == 2
        assert total_count == 2

    def test_all_lines_human(self, calculator, tracking):
        """Given no lines tracked, counts all as human."""
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line B"],
            tracking
        )

        assert ai_count == 0
        assert total_count == 2

    def test_mixed_ai_and_human(self, calculator, tracking, hasher):
        """Given mixed lines, counts each correctly."""
        tracking.add_ai_lines("file.py", ["line A"], hasher)
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line B"],
            tracking
        )

        assert ai_count == 1  # Only "line A" is AI
        assert total_count == 2

    def test_duplicate_lines_all_tracked(self, calculator, tracking, hasher):
        """Given duplicate lines all tracked as AI, counts all as AI."""
        # Track 3 occurrences of "line A"
        tracking.add_ai_lines("file.py", ["line A", "line A", "line A"], hasher)
        tracking.track_file("file.py")

        # Diff shows 3 occurrences
        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line A", "line A"],
            tracking
        )

        assert ai_count == 3
        assert total_count == 3

    def test_duplicate_lines_partially_tracked(self, calculator, tracking, hasher):
        """Given duplicate lines partially tracked, consumes tracked count correctly."""
        # Track only 2 occurrences of "line A"
        tracking.add_ai_lines("file.py", ["line A", "line A"], hasher)
        tracking.track_file("file.py")

        # Diff shows 3 occurrences
        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line A", "line A"],
            tracking
        )

        # Only 2 are AI (tracked count exhausted)
        assert ai_count == 2
        assert total_count == 3

    def test_duplicate_lines_over_tracked(self, calculator, tracking, hasher):
        """Given more occurrences tracked than in diff, counts only what's in diff."""
        # Track 5 occurrences of "line A"
        tracking.add_ai_lines("file.py", ["line A"] * 5, hasher)
        tracking.track_file("file.py")

        # Diff shows only 2 occurrences
        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["line A", "line A"],
            tracking
        )

        # Counts 2 (what's in diff)
        assert ai_count == 2
        assert total_count == 2

    def test_empty_lines_skipped(self, calculator, tracking):
        """Given empty lines, skips them from count."""
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_file_lines(
            "file.py",
            ["", "  ", "line A"],
            tracking
        )

        # Empty lines normalized to "" and skipped
        assert total_count == 1

    def test_multiple_files_isolated(self, calculator, tracking, hasher):
        """Given multiple files, counts are isolated per file."""
        tracking.add_ai_lines("file1.py", ["line A"], hasher)
        tracking.add_ai_lines("file2.py", ["line B"], hasher)
        tracking.track_file("file1.py")
        tracking.track_file("file2.py")

        # file1.py: "line A" is AI, "line B" is human
        ai_count1, total_count1 = calculator._count_file_lines(
            "file1.py",
            ["line A", "line B"],
            tracking
        )
        assert ai_count1 == 1
        assert total_count1 == 2

        # file2.py: "line B" is AI, "line A" is human
        ai_count2, total_count2 = calculator._count_file_lines(
            "file2.py",
            ["line A", "line B"],
            tracking
        )
        assert ai_count2 == 1
        assert total_count2 == 2


class TestCountRemovedLines:
    """Tests for _count_removed_lines method (removed lines attribution)."""

    def test_all_removals_by_ai(self, calculator, tracking, hasher):
        """Given all removals tracked, counts all as AI."""
        tracking.track_ai_removals("file.py", ["line A", "line B"], hasher)
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_removed_lines(
            "file.py",
            ["line A", "line B"],
            tracking
        )

        assert ai_count == 2
        assert total_count == 2

    def test_all_removals_by_human(self, calculator, tracking):
        """Given no removals tracked, counts all as human."""
        tracking.track_file("file.py")

        ai_count, total_count = calculator._count_removed_lines(
            "file.py",
            ["line A", "line B"],
            tracking
        )

        assert ai_count == 0
        assert total_count == 2

    def test_duplicate_removals_partially_tracked(self, calculator, tracking, hasher):
        """Given duplicate removals partially tracked, consumes correctly."""
        # Track 2 occurrences of removal
        tracking.track_ai_removals("file.py", ["removed", "removed"], hasher)
        tracking.track_file("file.py")

        # Diff shows 3 removals
        ai_count, total_count = calculator._count_removed_lines(
            "file.py",
            ["removed", "removed", "removed"],
            tracking
        )

        # Only 2 are AI (tracked count exhausted)
        assert ai_count == 2
        assert total_count == 3


class TestCalculate:
    """Integration tests for calculate method."""

    def test_single_file_all_ai(self, calculator, tracking, hasher):
        """Given single file all AI, calculates 100% AI."""
        tracking.add_ai_lines("file.py", ["line A", "line B"], hasher)
        tracking.track_file("file.py")

        # Create diff
        diff = Diff(
            merge_base="test-commit",
            files={
                "file.py": DiffFile(
                    file_path="file.py",
                    added_lines=["line A", "line B"],
                    removed_lines=[]
                )
            }
        )

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.total.lines == 2
        assert stats.ai_stats.total.percentage == 100.0
        assert stats.human_stats.total.lines == 0
        assert stats.human_stats.total.percentage == 0.0

    def test_single_file_mixed(self, calculator, tracking, hasher):
        """Given single file mixed AI/human, calculates correctly."""
        # 1 AI line out of 2
        tracking.add_ai_lines("file.py", ["line A"], hasher)
        tracking.track_file("file.py")

        diff = Diff(
            merge_base="test-commit",
            files={
                "file.py": DiffFile(
                    file_path="file.py",
                    added_lines=["line A", "line B"],
                    removed_lines=[]
                )
            }
        )

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.added.lines == 1
        assert stats.ai_stats.added.percentage == 50.0
        assert stats.human_stats.added.lines == 1
        assert stats.human_stats.added.percentage == 50.0

    def test_duplicate_lines_in_diff(self, calculator, tracking, hasher):
        """Given duplicate lines in diff, calculates based on tracked counts."""
        # Track 2 occurrences of "line A"
        tracking.add_ai_lines("file.py", ["line A", "line A"], hasher)
        tracking.track_file("file.py")

        # Diff shows 3 occurrences (2 AI, 1 human)
        diff = Diff(
            merge_base="test-commit",
            files={
                "file.py": DiffFile(
                    file_path="file.py",
                    added_lines=["line A", "line A", "line A"],
                    removed_lines=[]
                )
            }
        )

        stats = calculator.calculate(tracking, diff)

        # 2 AI lines (tracked count), 1 human line
        assert stats.ai_stats.added.lines == 2
        assert stats.human_stats.added.lines == 1
        assert stats.ai_stats.added.percentage == 66.7  # 2/3 * 100

    def test_file_type_aggregation(self, calculator, tracking, hasher):
        """Given multiple file types, aggregates by extension."""
        tracking.add_ai_lines("file.py", ["py line"], hasher)
        tracking.add_ai_lines("file.js", ["js line"], hasher)
        tracking.track_file("file.py")
        tracking.track_file("file.js")

        diff = Diff(
            merge_base="test-commit",
            files={
                "file.py": DiffFile("file.py", ["py line"], []),
                "file.js": DiffFile("file.js", ["js line"], [])
            }
        )

        stats = calculator.calculate(tracking, diff)

        assert ".py" in stats.by_file_type
        assert ".js" in stats.by_file_type
        assert stats.by_file_type[".py"].ai_lines == 1
        assert stats.by_file_type[".js"].ai_lines == 1
