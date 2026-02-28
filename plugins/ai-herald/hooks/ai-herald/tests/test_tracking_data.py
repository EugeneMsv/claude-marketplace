"""Tests for TrackingData."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.tracking_data import TrackingData
from domain.line_hasher import LineHasher


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def tracking():
    return TrackingData("test-branch")


class TestAddAiLines:
    """Tests for add_ai_lines method."""

    def test_adds_single_line(self, tracking, hasher):
        """Given single line, adds with count 1."""
        tracking.add_ai_lines("file.py", ["line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert len(hashes) == 1
        assert list(hashes.values()) == [1]

    def test_adds_duplicate_lines(self, tracking, hasher):
        """Given duplicate lines, increments count."""
        tracking.add_ai_lines("file.py", ["line A", "line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert len(hashes) == 1
        line_hash = list(hashes.keys())[0]
        assert hashes[line_hash] == 2

    def test_adds_multiple_unique_lines(self, tracking, hasher):
        """Given unique lines, adds each with count 1."""
        tracking.add_ai_lines("file.py", ["line A", "line B", "line C"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert len(hashes) == 3
        assert all(count == 1 for count in hashes.values())

    def test_adds_mixed_unique_and_duplicate(self, tracking, hasher):
        """Given mix of unique and duplicate, tracks counts correctly."""
        tracking.add_ai_lines("file.py", ["line A", "line B", "line A", "line C"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert len(hashes) == 3

        # Find the hash for "line A" and verify count is 2
        line_a_hash = hasher.hash("line A")
        assert hashes[line_a_hash] == 2

        # Other lines should have count 1
        line_b_hash = hasher.hash("line B")
        line_c_hash = hasher.hash("line C")
        assert hashes[line_b_hash] == 1
        assert hashes[line_c_hash] == 1

    def test_increments_on_subsequent_calls(self, tracking, hasher):
        """Given multiple calls with same line, increments count."""
        tracking.add_ai_lines("file.py", ["line A"], hasher)
        tracking.add_ai_lines("file.py", ["line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        line_hash = hasher.hash("line A")
        assert hashes[line_hash] == 2

    def test_different_files_tracked_separately(self, tracking, hasher):
        """Given different files, tracks counts separately."""
        tracking.add_ai_lines("file1.py", ["line A"], hasher)
        tracking.add_ai_lines("file2.py", ["line A", "line A"], hasher)

        hashes1 = tracking.get_ai_hashes_for_file("file1.py")
        hashes2 = tracking.get_ai_hashes_for_file("file2.py")

        line_hash = hasher.hash("line A")
        assert hashes1[line_hash] == 1
        assert hashes2[line_hash] == 2

    def test_skips_empty_lines(self, tracking, hasher):
        """Given empty lines, skips them (after normalization)."""
        tracking.add_ai_lines("file.py", ["", "   ", "line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        # Empty/whitespace lines normalize to empty string and are skipped
        assert len(hashes) == 1


class TestAddAiLineHash:
    """Tests for add_ai_line_hash method."""

    def test_adds_single_hash(self, tracking):
        """Given single hash, adds with count 1."""
        tracking.add_ai_line_hash("file.py", "hash123")

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert hashes["hash123"] == 1

    def test_adds_with_custom_count(self, tracking):
        """Given custom count, adds that many occurrences."""
        tracking.add_ai_line_hash("file.py", "hash123", count=5)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert hashes["hash123"] == 5

    def test_increments_existing_hash(self, tracking):
        """Given existing hash, increments count."""
        tracking.add_ai_line_hash("file.py", "hash123", count=2)
        tracking.add_ai_line_hash("file.py", "hash123", count=3)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert hashes["hash123"] == 5


class TestRemoveAiLines:
    """Tests for remove_ai_lines method."""

    def test_decrements_count(self, tracking, hasher):
        """Given line with count > 1, decrements count."""
        tracking.add_ai_lines("file.py", ["line A", "line A", "line A"], hasher)
        tracking.remove_ai_lines("file.py", ["line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        line_hash = hasher.hash("line A")
        assert hashes[line_hash] == 2

    def test_removes_when_count_reaches_zero(self, tracking, hasher):
        """Given line with count 1, removes hash when decremented."""
        tracking.add_ai_lines("file.py", ["line A"], hasher)
        tracking.remove_ai_lines("file.py", ["line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert len(hashes) == 0

    def test_handles_duplicate_removals(self, tracking, hasher):
        """Given multiple removals of same line, decrements by each."""
        tracking.add_ai_lines("file.py", ["line A", "line A", "line A"], hasher)
        tracking.remove_ai_lines("file.py", ["line A", "line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        line_hash = hasher.hash("line A")
        assert hashes[line_hash] == 1

    def test_safe_when_removing_nonexistent(self, tracking, hasher):
        """Given line not in tracking, removal is safe (no error)."""
        tracking.remove_ai_lines("file.py", ["line A"], hasher)
        # Should not raise an error

    def test_safe_when_file_not_tracked(self, tracking, hasher):
        """Given file not tracked, removal is safe (no error)."""
        tracking.remove_ai_lines("nonexistent.py", ["line A"], hasher)
        # Should not raise an error


class TestTrackAiRemovals:
    """Tests for track_ai_removals method."""

    def test_tracks_single_removal(self, tracking, hasher):
        """Given single removal, tracks with count 1."""
        tracking.track_ai_removals("file.py", ["removed line"], hasher)

        removed = tracking.get_ai_removed_hashes_for_file("file.py")
        assert len(removed) == 1
        assert list(removed.values()) == [1]

    def test_tracks_duplicate_removals(self, tracking, hasher):
        """Given duplicate removals, increments count."""
        tracking.track_ai_removals("file.py", ["removed", "removed"], hasher)

        removed = tracking.get_ai_removed_hashes_for_file("file.py")
        line_hash = hasher.hash("removed")
        assert removed[line_hash] == 2

    def test_increments_on_subsequent_calls(self, tracking, hasher):
        """Given multiple calls, increments removal count."""
        tracking.track_ai_removals("file.py", ["removed"], hasher)
        tracking.track_ai_removals("file.py", ["removed"], hasher)

        removed = tracking.get_ai_removed_hashes_for_file("file.py")
        line_hash = hasher.hash("removed")
        assert removed[line_hash] == 2


class TestGetAiHashesForFile:
    """Tests for get_ai_hashes_for_file method."""

    def test_returns_empty_dict_for_untracked_file(self, tracking):
        """Given file not in tracking, returns empty dict."""
        hashes = tracking.get_ai_hashes_for_file("nonexistent.py")
        assert hashes == {}

    def test_returns_copy_not_reference(self, tracking, hasher):
        """Returned dict is a copy, modifying it doesn't affect tracking."""
        tracking.add_ai_lines("file.py", ["line A"], hasher)

        hashes = tracking.get_ai_hashes_for_file("file.py")
        hashes["new_hash"] = 999

        # Original should be unchanged
        hashes_again = tracking.get_ai_hashes_for_file("file.py")
        assert "new_hash" not in hashes_again
