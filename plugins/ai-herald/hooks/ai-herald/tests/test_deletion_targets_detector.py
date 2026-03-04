"""Tests for DeletionTargetsDetector."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.deletion_targets_detector import DeletionTargetsDetector


class TestDeletionTargetsDetector:
    """Tests for DeletionTargetsDetector.detect() method."""

    @pytest.mark.parametrize("command, expected", [
        # Simple rm
        ("rm file.py",                       {"file.py"}),
        # rm with flags
        ("rm -f file.py",                    {"file.py"}),
        ("rm -rf src/old/components/",       {"src/old/components/"}),
        # Multiple targets
        ("rm a.py b.py",                     {"a.py", "b.py"}),
        # git rm
        ("git rm domain/old.py",             {"domain/old.py"}),
        ("git rm -r domain/",                {"domain/"}),
        # unlink
        ("unlink x.txt",                     {"x.txt"}),
        # Chained commands — only deletion part extracted
        ("git commit -m 'x' && rm file.py",  {"file.py"}),
        ("rm a.py; rm b.py",                 {"a.py", "b.py"}),
        # Pure commit — no deletion targets
        ("git commit -m 'x'",                set()),
        # Empty string
        ("",                                 set()),
    ])
    def test_detect(self, command, expected):
        """Given a bash command, detect returns expected path tokens."""
        assert DeletionTargetsDetector().detect(command) == expected
