"""Tests for CaptureService."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.capture_service import CaptureService


class TestDiffLines:
    """Tests for _diff_lines method."""

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
