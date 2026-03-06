"""Tests for StatsCalculator."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.stats_calculator import StatsCalculator
from domain.generated_code_detector import GeneratedCodeDetector
from domain.tracking_data import TrackingData
from domain.diff import Diff, DiffFile
from domain.line_hasher import LineHasher


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def no_op_detector():
    """GeneratedCodeDetector that never matches anything."""
    return GeneratedCodeDetector(set())


@pytest.fixture
def calculator(hasher, no_op_detector):
    return StatsCalculator(hasher, {'.py', '.java', '.kt', '.js', '.ts'}, no_op_detector)


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


class TestCalculateHumanOnlyFiles:
    """Tests for files changed in the diff but never touched by AI tools."""

    def test_manually_edited_file_counted_as_human(self, hasher, tracking, no_op_detector):
        """Given a file absent from files_tracked with a tracked extension,
        all changed lines from the diff are attributed to human."""
        calculator = StatsCalculator(hasher, {'.py'}, no_op_detector)
        diff = Diff("abc123", {
            "src/service.py": DiffFile("src/service.py", ["def foo():", "    return 42"], [])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.human_stats.added.lines == 2
        assert stats.ai_stats.added.lines == 0

    def test_mixed_ai_tracked_and_human_only_files(self, hasher, tracking, no_op_detector):
        """Given one AI-tracked file and one human-only file,
        stats correctly split attribution across both."""
        calculator = StatsCalculator(hasher, {'.py'}, no_op_detector)
        ai_line = "def ai_func(): pass"
        tracking.add_ai_lines("src/ai.py", [ai_line], hasher)
        tracking.track_file("src/ai.py")

        diff = Diff("abc123", {
            "src/ai.py": DiffFile("src/ai.py", [ai_line], []),
            "src/human.py": DiffFile("src/human.py", ["def human_func(): pass", "    return 1"], []),
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.added.lines == 1
        assert stats.human_stats.added.lines == 2

    def test_untracked_extension_excluded(self, hasher, tracking, no_op_detector):
        """Files with extensions not in tracked_extensions are excluded entirely."""
        calculator = StatsCalculator(hasher, {'.py'}, no_op_detector)
        diff = Diff("abc123", {
            "README.md": DiffFile("README.md", ["# Title", "some text"], [])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.human_stats.added.lines == 0
        assert stats.ai_stats.added.lines == 0

    def test_human_only_file_removals_counted(self, hasher, tracking, no_op_detector):
        """Given a human-only file with removed lines, removals are attributed to human."""
        calculator = StatsCalculator(hasher, {'.py'}, no_op_detector)
        diff = Diff("abc123", {
            "src/old.py": DiffFile("src/old.py", [], ["def old_func(): pass", "    pass"])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.human_stats.removed.lines == 2
        assert stats.ai_stats.removed.lines == 0


class TestCalculateCodeGenRouting:
    """Tests for code-generated file routing in StatsCalculator."""

    def test_code_gen_file_excluded_from_ai_human_totals(self, hasher, tracking):
        """Given an AI-tracked file matching a code-gen pattern, it goes to code-gen bucket."""
        detector = GeneratedCodeDetector({"**/generated/**"})
        calculator = StatsCalculator(hasher, {'.java'}, detector)
        tracking.add_ai_lines("src/generated/Foo.java", ["line A", "line B"], hasher)
        tracking.track_file("src/generated/Foo.java")

        diff = Diff("abc123", {
            "src/generated/Foo.java": DiffFile(
                "src/generated/Foo.java", ["line A", "line B"], []
            )
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.total.lines == 0
        assert stats.human_stats.total.lines == 0
        assert stats.code_generated.total == 2
        assert stats.code_generated.added == 2
        assert stats.code_generated.removed == 0
        assert "**/generated/**" in stats.code_generated.matched_patterns

    def test_human_only_code_gen_file_excluded(self, hasher, tracking):
        """Given a human-only file matching a code-gen pattern, it goes to code-gen bucket."""
        detector = GeneratedCodeDetector({"**/generated/**"})
        calculator = StatsCalculator(hasher, {'.java'}, detector)

        diff = Diff("abc123", {
            "src/generated/Bar.java": DiffFile(
                "src/generated/Bar.java", ["line X", "line Y", "line Z"], []
            )
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.total.lines == 0
        assert stats.human_stats.total.lines == 0
        assert stats.code_generated.total == 3
        assert "**/generated/**" in stats.code_generated.matched_patterns

    def test_non_code_gen_file_not_affected(self, hasher, tracking):
        """Given a regular file, it is unaffected by the code-gen detector."""
        detector = GeneratedCodeDetector({"**/generated/**"})
        calculator = StatsCalculator(hasher, {'.py'}, detector)
        tracking.add_ai_lines("src/main/Foo.py", ["def foo(): pass"], hasher)
        tracking.track_file("src/main/Foo.py")

        diff = Diff("abc123", {
            "src/main/Foo.py": DiffFile("src/main/Foo.py", ["def foo(): pass"], [])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.total.lines == 1
        assert stats.code_generated.total == 0

    def test_mixed_regular_and_code_gen_files(self, hasher, tracking):
        """Given mixed files, code-gen lines excluded from AI/human denominator."""
        detector = GeneratedCodeDetector({"**/generated/**"})
        calculator = StatsCalculator(hasher, {'.java'}, detector)

        tracking.add_ai_lines("src/main/Service.java", ["line A"], hasher)
        tracking.track_file("src/main/Service.java")

        diff = Diff("abc123", {
            "src/main/Service.java": DiffFile("src/main/Service.java", ["line A"], []),
            "src/generated/Client.java": DiffFile("src/generated/Client.java", ["gen A", "gen B"], []),
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.ai_stats.total.lines == 1
        assert stats.human_stats.total.lines == 0
        assert stats.code_generated.total == 2

    def test_code_gen_removals_tracked_in_code_gen_bucket(self, hasher, tracking):
        """Given code-gen file with removed lines, removals go to code-gen bucket."""
        detector = GeneratedCodeDetector({"**/generated/**"})
        calculator = StatsCalculator(hasher, {'.java'}, detector)

        diff = Diff("abc123", {
            "src/generated/Old.java": DiffFile("src/generated/Old.java", [], ["old gen line"])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.code_generated.removed == 1
        assert stats.ai_stats.removed.lines == 0
        assert stats.human_stats.removed.lines == 0

    def test_no_detector_patterns_routes_all_to_ai_human(self, hasher, tracking):
        """Given empty pattern set, no files routed to code-gen bucket."""
        detector = GeneratedCodeDetector(set())
        calculator = StatsCalculator(hasher, {'.java'}, detector)

        diff = Diff("abc123", {
            "src/generated/Foo.java": DiffFile("src/generated/Foo.java", ["line A"], [])
        })

        stats = calculator.calculate(tracking, diff)

        assert stats.code_generated.total == 0
        assert stats.human_stats.total.lines == 1
