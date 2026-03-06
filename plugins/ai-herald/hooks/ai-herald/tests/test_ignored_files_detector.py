"""Tests for IgnoredFilesDetector."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.ignored_files_detector import IgnoredFilesDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detector(*patterns: str) -> IgnoredFilesDetector:
    return IgnoredFilesDetector(set(patterns))


# ---------------------------------------------------------------------------
# Depth & hierarchy for **/generated/**
# ---------------------------------------------------------------------------

class TestGeneratedDirPattern:
    """Tests for '**/generated/**' — files under generated/ at any depth."""

    PATTERN = "**/generated/**"

    @pytest.mark.parametrize("path,expected", [
        # L1 (root-level generated dir)
        ("generated/file1.java", True),
        # L2 (one parent dir)
        ("somefolder/generated/file1.java", True),
        # L2 sub-L1 (one level inside generated)
        ("somefolder/generated/subfolder/file2.java", True),
        # L2 sub-L2 (two levels inside generated)
        ("somefolder/generated/subfolder/subfolder2/file3.java", True),
        # L3 parent + deep nesting
        ("com/example/generated/sub/deep/Foo.java", True),
        # Different tracked extensions
        ("somefolder/generated/Foo.ts", True),
        ("somefolder/generated/Foo.py", True),
        # Sibling file — not inside generated
        ("somefolder/Foo.java", False),
        # File next to generated dir
        ("com/example/Foo.java", False),
        # Dirname that contains 'generated' but differs
        ("somefolder/mygenerated/Foo.java", False),
        # Dirname with generated as prefix
        ("somefolder/generated_utils/Foo.java", False),
    ])
    def test_is_ignored(self, path, expected):
        """Given path and **/generated/** pattern, is_ignored returns expected."""
        detector = _detector(self.PATTERN)
        assert detector.is_ignored(path) is expected


# ---------------------------------------------------------------------------
# Extension-based pattern **/*.generated.ts
# ---------------------------------------------------------------------------

class TestGeneratedExtensionPattern:
    """Tests for '**/*.generated.ts' — files ending with .generated.ts."""

    PATTERN = "**/*.generated.ts"

    @pytest.mark.parametrize("path,expected", [
        # L1: root
        ("Foo.generated.ts", True),
        # L2
        ("src/Foo.generated.ts", True),
        # L3
        ("src/api/Foo.generated.ts", True),
        # Missing dot before 'ts'
        ("src/api/Foo.generatedts", False),
        # Different extension
        ("src/api/Foo.generated.js", False),
    ])
    def test_is_ignored(self, path, expected):
        """Given path and **/*.generated.ts pattern, is_ignored returns expected."""
        detector = _detector(self.PATTERN)
        assert detector.is_ignored(path) is expected


# ---------------------------------------------------------------------------
# Suffix-based pattern **/*_pb2.py
# ---------------------------------------------------------------------------

class TestPb2SuffixPattern:
    """Tests for '**/*_pb2.py' — protobuf generated Python files."""

    PATTERN = "**/*_pb2.py"

    @pytest.mark.parametrize("path,expected", [
        # Root
        ("foo_pb2.py", True),
        # One level deep
        ("proto/foo_pb2.py", True),
        # Deep
        ("proto/generated/bar_pb2.py", True),
        # Different suffix
        ("proto/foo_pb2_grpc.py", False),
    ])
    def test_is_ignored(self, path, expected):
        """Given path and **/*_pb2.py pattern, is_ignored returns expected."""
        detector = _detector(self.PATTERN)
        assert detector.is_ignored(path) is expected


# ---------------------------------------------------------------------------
# Scoped directory pattern **/build/generated/**
# ---------------------------------------------------------------------------

class TestBuildGeneratedPattern:
    """Tests for '**/build/generated/**' — files under build/generated/ at any depth."""

    PATTERN = "**/build/generated/**"

    @pytest.mark.parametrize("path,expected", [
        # Root-level build
        ("build/generated/Foo.java", True),
        # Module-level build
        ("module/build/generated/Foo.java", True),
        # File under sub
        ("module/build/generated/sub/Foo.java", True),
        # In build but not in generated sub
        ("build/Foo.java", False),
        # Generated at root, not under build
        ("generated/Foo.java", False),
    ])
    def test_is_ignored(self, path, expected):
        """Given path and **/build/generated/** pattern, is_ignored returns expected."""
        detector = _detector(self.PATTERN)
        assert detector.is_ignored(path) is expected


# ---------------------------------------------------------------------------
# matched_patterns() tests
# ---------------------------------------------------------------------------

class TestMatchedPatterns:
    """Tests for matched_patterns() — returns all matching patterns."""

    def test_file_matching_two_patterns_returns_both(self):
        """Given file matching both **/generated/** and **/*.generated.ts, returns both."""
        detector = _detector("**/generated/**", "**/*.generated.ts")
        result = detector.matched_patterns("src/generated/Foo.generated.ts")
        assert result == {"**/generated/**", "**/*.generated.ts"}

    def test_file_matching_one_pattern_returns_singleton(self):
        """Given file matching only one pattern, returns singleton set."""
        detector = _detector("**/generated/**", "**/*.generated.ts")
        result = detector.matched_patterns("src/generated/Foo.java")
        assert result == {"**/generated/**"}

    def test_non_matching_file_returns_empty_set(self):
        """Given non-matching file, returns empty set."""
        detector = _detector("**/generated/**", "**/*.generated.ts")
        result = detector.matched_patterns("src/main/Foo.java")
        assert result == set()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for IgnoredFilesDetector."""

    def test_empty_pattern_set_is_ignored_returns_false(self):
        """Given empty pattern set, is_ignored returns False."""
        detector = IgnoredFilesDetector(set())
        assert detector.is_ignored("generated/Foo.java") is False

    def test_empty_pattern_set_matched_patterns_returns_empty(self):
        """Given empty pattern set, matched_patterns returns empty set."""
        detector = IgnoredFilesDetector(set())
        assert detector.matched_patterns("generated/Foo.java") == set()

    def test_path_with_no_extension_matches_dir_pattern(self):
        """Given path with no extension inside generated/, matches dir pattern."""
        detector = _detector("**/generated/**")
        assert detector.is_ignored("generated/MAKEFILE") is True

    def test_windows_style_path_normalized_to_forward_slash(self):
        """Given Windows-style backslash path, normalizes to / before matching."""
        detector = _detector("**/generated/**")
        assert detector.is_ignored("src\\generated\\Foo.java") is True

    def test_is_ignored_short_circuits_on_first_match(self):
        """Given multiple patterns where first matches, returns True without checking rest."""
        detector = _detector("**/generated/**", "**/__generated__/**")
        # Both could match but should return True on first match
        assert detector.is_ignored("src/generated/Foo.java") is True

    def test_path_object_accepted(self):
        """Given a Path object, is_ignored works correctly."""
        detector = _detector("**/generated/**")
        assert detector.is_ignored(Path("src/generated/Foo.java")) is True
