"""Tests for CaptureService."""

import sys
import tempfile
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.capture_service import CaptureService
from domain.line_hasher import LineHasher
from domain.tracking_data import TrackingData
from infrastructure.tracking_repository import TrackingRepository
from infrastructure.git_repository import GitRepository


class TestDiffLines:
    """Tests for _diff_lines static method."""

    def test_no_duplicates_basic_case(self):
        """Given unique lines in both old and new, returns only new unique lines."""
        old = "line A\nline B"
        new = "line A\nline B\nline C"

        result = CaptureService._diff_lines(old, new)
        assert result == ["line C"]

    def test_duplicate_in_new_only(self):
        """Given duplicate lines only in new content, captures all occurrences."""
        old = "line A\nline B"
        new = "line A\nline B\nline C\nline C"

        result = CaptureService._diff_lines(old, new)
        assert sorted(result) == ["line C", "line C"]

    def test_duplicate_in_both_old_and_new(self):
        """Given duplicate in both, captures only the additional occurrences."""
        old = "line A\nline A\nline B"
        new = "line A\nline A\nline A\nline B"

        result = CaptureService._diff_lines(old, new)
        assert result == ["line A"]  # One additional "line A"

    def test_duplicate_removed(self):
        """Given fewer occurrences in new than old, returns empty."""
        old = "line A\nline A\nline A"
        new = "line A\nline A"

        result = CaptureService._diff_lines(old, new)
        assert result == []

    def test_all_duplicates(self):
        """Given all duplicate lines added, captures all."""
        old = "line A"
        new = "line A\nline A\nline A\nline A"

        result = CaptureService._diff_lines(old, new)
        assert len(result) == 3  # 3 additional "line A"
        assert all(line == "line A" for line in result)

    def test_mixed_duplicates_and_unique(self):
        """Given mix of duplicate and unique lines, captures correctly."""
        old = "line A\nline B"
        new = "line A\nline B\nline C\nline C\nline D"

        result = CaptureService._diff_lines(old, new)
        assert sorted(result) == ["line C", "line C", "line D"]

    def test_empty_old_content(self):
        """Given empty old content, captures all lines from new."""
        old = ""
        new = "line A\nline A\nline B"

        result = CaptureService._diff_lines(old, new)
        assert sorted(result) == ["line A", "line A", "line B"]

    def test_empty_new_content(self):
        """Given empty new content, returns empty list."""
        old = "line A\nline B"
        new = ""

        result = CaptureService._diff_lines(old, new)
        assert result == []

    def test_both_empty(self):
        """Given both empty, returns empty list."""
        old = ""
        new = ""

        result = CaptureService._diff_lines(old, new)
        assert result == []

    def test_identical_content(self):
        """Given identical content, returns empty list."""
        old = "line A\nline B\nline C"
        new = "line A\nline B\nline C"

        result = CaptureService._diff_lines(old, new)
        assert result == []

    def test_real_world_method_addition(self):
        """Test real-world scenario: adding new method with duplicate boilerplate."""
        old = '''def method1():
    """Docstring"""
    try:
        return True'''

        new = '''def method1():
    """Docstring"""
    try:
        return True

def method2():
    """Docstring"""
    try:
        return True'''

        result = CaptureService._diff_lines(old, new)

        # Should capture: empty line, def method2():, """Docstring""" (with indent),
        # try: (with indent), return True (with indent)
        assert len(result) == 5
        assert '    """Docstring"""' in result  # With indentation
        assert '    try:' in result
        assert '        return True' in result
        assert 'def method2():' in result
        assert '' in result  # Empty line

    def test_whitespace_matters(self):
        """Different whitespace = different lines, should be captured separately."""
        old = "  line A"
        new = "  line A\n    line A"  # Different indentation

        result = CaptureService._diff_lines(old, new)
        assert result == ["    line A"]  # Only the differently-indented one

    def test_multiple_occurrences(self):
        """Multiple occurrences of same line are captured correctly."""
        old = "line A"
        new = "line A\nline B\nline C\nline B"

        result = CaptureService._diff_lines(old, new)
        # Should have: 2x "line B" and 1x "line C"
        # Note: Counter.elements() doesn't guarantee order
        assert sorted(result) == ["line B", "line B", "line C"]
        assert result.count("line B") == 2
        assert result.count("line C") == 1


def _make_service(git_root: Path, branch: str = "feature/test", tracked_ext=".py"):
    """Build a CaptureService wired to a real temp git_root."""
    git_repo = MagicMock()
    git_repo.get_root.return_value = git_root
    git_repo.get_current_branch.return_value = branch
    git_repo.sanitize_branch_name = GitRepository.sanitize_branch_name

    config = MagicMock()
    config.should_track_file.side_effect = lambda p: p.suffix.lower() == tracked_ext

    hasher = LineHasher()
    logger = logging.getLogger("test")

    return CaptureService(git_repo, config, hasher, logger)


class TestProcessWrite:
    """Tests for process_write."""

    def test_write_tracks_content_lines(self):
        """Given a Write event, each content line is tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_root = Path(tmpdir)
            (git_root / ".claude").mkdir()
            service = _make_service(git_root)

            tool_input = {"file_path": str(git_root / "app.py"), "content": "line A\nline B\nline C"}
            result = service.process_write(tool_input)

            assert result is True
            tracking_repo = TrackingRepository(git_root, "feature-test")
            tracking = tracking_repo.load()
            assert tracking is not None
            assert "app.py" in tracking.files_tracked

    def test_write_empty_file_path_returns_false(self):
        """Given no file_path in input, returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _make_service(Path(tmpdir))
            result = service.process_write({"content": "some content"})
            assert result is False

    def test_write_untracked_extension_returns_false(self):
        """Given file with untracked extension, returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_root = Path(tmpdir)
            service = _make_service(git_root)  # only .py tracked

            tool_input = {"file_path": str(git_root / "readme.md"), "content": "hello"}
            result = service.process_write(tool_input)
            assert result is False


class TestProcessEdit:
    """Tests for process_edit."""

    def test_edit_tracks_added_lines(self):
        """Given an Edit event, newly added lines are tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_root = Path(tmpdir)
            (git_root / ".claude").mkdir()
            service = _make_service(git_root)

            tool_input = {
                "file_path": str(git_root / "app.py"),
                "old_string": "line A",
                "new_string": "line A\nline B",
            }
            result = service.process_edit(tool_input)

            assert result is True
            tracking_repo = TrackingRepository(git_root, "feature-test")
            tracking = tracking_repo.load()
            assert tracking is not None
            assert "app.py" in tracking.files_tracked

    def test_edit_empty_file_path_returns_false(self):
        """Given no file_path in input, returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _make_service(Path(tmpdir))
            result = service.process_edit({"old_string": "a", "new_string": "b"})
            assert result is False
