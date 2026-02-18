"""Tests for FormatTrackerService."""

import sys
from pathlib import Path
import pytest
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.format_tracker_service import FormatTrackerService
from domain.tracking_data import TrackingData
from domain.format_snapshot import FormatSnapshot
from domain.line_hasher import LineHasher
from domain.token_normalizer import TokenNormalizer
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository
from logging import Logger, INFO
import logging


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        # Create .git directory to simulate git repo
        (temp_path / '.git').mkdir()
        yield temp_path


@pytest.fixture
def logger():
    """Create logger for tests."""
    logger = logging.getLogger("test")
    logger.setLevel(INFO)
    return logger


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def token_normalizer():
    return TokenNormalizer()


@pytest.fixture
def git_repo():
    """Create git repo instance."""
    return GitRepository()


@pytest.fixture
def config():
    """Create minimal config."""
    return Configuration(
        enabled=True,
        base_branches=['main'],
        tracked_extensions={'.py', '.js'},
        enable_logging=False,
        log_file='test.log',
        format_detection_enabled=True
    )


@pytest.fixture
def format_tracker(git_repo, config, hasher, token_normalizer, logger):
    """Create format tracker service.

    Note: For these tests, we'll call _process_file directly with temp_dir,
    bypassing the need for actual git operations.
    """
    return FormatTrackerService(git_repo, config, hasher, token_normalizer, logger)


class TestProcessFile:
    """Tests for _process_file method."""

    def test_preserves_duplicate_counts(self, format_tracker, temp_dir, hasher):
        """Given formatted file with duplicates, preserves occurrence counts."""
        # Create tracking data
        tracking = TrackingData("test-branch")

        # Create test file with duplicate lines (after formatting with 4-space indent)
        test_file = temp_dir / "test.py"
        test_file.write_text(
            'def method1():\n'
            '    """Docstring"""\n'
            '    pass\n'
            '\n'
            'def method2():\n'
            '    """Docstring"""\n'
            '    pass\n'
            '\n'
            'def method3():\n'
            '    """Docstring"""\n'
            '    pass\n'
        )

        # Create snapshot (simulating pre-format state with 2-space indent)
        # Include all three methods for high token overlap
        old_content = (
            'def method1():\n'
            '  """Docstring"""\n'
            '  pass\n'
            '\n'
            'def method2():\n'
            '  """Docstring"""\n'
            '  pass\n'
            '\n'
            'def method3():\n'
            '  """Docstring"""\n'
            '  pass\n'
        )
        old_hash1 = hasher.hash('  """Docstring"""')
        old_hash2 = hasher.hash('def method1():')
        old_hash3 = hasher.hash('def method2():')
        hash_to_content = {
            old_hash1: old_content,
            old_hash2: old_content,
            old_hash3: old_content
        }

        # Process file
        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        assert updated

        # Verify duplicate counts preserved
        hashes = tracking.get_ai_hashes_for_file("test.py")
        docstring_hash = hasher.hash('    """Docstring"""')

        # Should have count=3 for the docstring line
        assert docstring_hash in hashes
        assert hashes[docstring_hash] == 3

    def test_handles_single_occurrence(self, format_tracker, temp_dir, hasher):
        """Given file with single occurrence, tracks with count=1."""
        tracking = TrackingData("test-branch")

        test_file = temp_dir / "test.py"
        test_file.write_text('def method():\n    pass\n')

        old_content = 'def method():\n  pass\n'
        old_hash = hasher.hash('def method():')
        hash_to_content = {old_hash: old_content}

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        assert updated

        hashes = tracking.get_ai_hashes_for_file("test.py")
        pass_hash = hasher.hash('    pass')
        assert hashes[pass_hash] == 1

    def test_adds_all_unique_lines(self, format_tracker, temp_dir, hasher):
        """Given file with multiple unique lines, tracks all with counts."""
        tracking = TrackingData("test-branch")

        # Use more realistic content with enough tokens for good overlap
        test_file = temp_dir / "test.py"
        test_file.write_text(
            'def calculate_total_price(items):\n'
            '    """Calculate total."""\n'
            '    total = 0\n'
            '    for item in items:\n'
            '        total += item.price\n'
            '    return total\n'
            '\n'
            'def calculate_total_tax(items):\n'
            '    """Calculate total."""\n'
            '    total = 0\n'
            '    for item in items:\n'
            '        total += item.tax\n'
            '    return total\n'
        )

        # Snapshot with slightly different formatting but same content
        old_content = test_file.read_text().replace('    ', '  ')
        old_hash = hasher.hash('def calculate_total_price(items):')
        hash_to_content = {old_hash: old_content}

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        assert updated

        hashes = tracking.get_ai_hashes_for_file("test.py")

        # Verify counts for duplicate lines
        docstring_hash = hasher.hash('    """Calculate total."""')
        total_zero_hash = hasher.hash('    total = 0')
        for_loop_hash = hasher.hash('    for item in items:')
        return_hash = hasher.hash('    return total')

        # Each appears twice in the file
        assert hashes[docstring_hash] == 2
        assert hashes[total_zero_hash] == 2
        assert hashes[for_loop_hash] == 2
        assert hashes[return_hash] == 2

    def test_low_token_overlap_returns_false(self, format_tracker, temp_dir, hasher):
        """Given low token overlap, doesn't update tracking."""
        tracking = TrackingData("test-branch")

        # Create file with completely different content
        test_file = temp_dir / "test.py"
        test_file.write_text('completely different content\n')

        # Snapshot has different content
        old_content = 'original content that is very different\n'
        old_hash = hasher.hash('original content')
        hash_to_content = {old_hash: old_content}

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        # Should not update due to low token overlap
        assert not updated

        # Tracking should be empty
        hashes = tracking.get_ai_hashes_for_file("test.py")
        assert len(hashes) == 0

    def test_skips_empty_lines(self, format_tracker, temp_dir, hasher):
        """Given file with empty lines, doesn't track them."""
        tracking = TrackingData("test-branch")

        test_file = temp_dir / "test.py"
        test_file.write_text(
            '\n'
            '   \n'
            'line A\n'
            '\n'
        )

        old_content = '\n   \nline A\n\n'
        old_hash = hasher.hash('line A')
        hash_to_content = {old_hash: old_content}

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        assert updated

        hashes = tracking.get_ai_hashes_for_file("test.py")

        # Only "line A" should be tracked (empty lines skipped)
        assert len(hashes) == 1
        line_a_hash = hasher.hash('line A')
        assert hashes[line_a_hash] == 1

    def test_nonexistent_file_returns_false(self, format_tracker, temp_dir, hasher):
        """Given nonexistent file, returns False."""
        tracking = TrackingData("test-branch")

        hash_to_content = {"hash1": "content"}

        updated = format_tracker._process_file(
            temp_dir,
            "nonexistent.py",
            hash_to_content,
            tracking
        )

        assert not updated

    def test_empty_hash_to_content_returns_false(self, format_tracker, temp_dir):
        """Given empty hash_to_content, returns False."""
        tracking = TrackingData("test-branch")

        test_file = temp_dir / "test.py"
        test_file.write_text('line A\n')

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            {},
            tracking
        )

        assert not updated


class TestIntegration:
    """Integration tests for format tracker."""

    def test_real_world_formatting_scenario(self, format_tracker, temp_dir, hasher):
        """Test realistic formatting scenario with method addition."""
        tracking = TrackingData("test-branch")

        # Simulate file after formatting (with duplicate docstrings and try blocks)
        test_file = temp_dir / "test.py"
        test_file.write_text(
            'def method1():\n'
            '    """Docstring"""\n'
            '    try:\n'
            '        return True\n'
            '\n'
            'def method2():\n'
            '    """Docstring"""\n'
            '    try:\n'
            '        return False\n'
        )

        # Snapshot from pre-format state (include both methods for high token overlap)
        old_content = (
            'def method1():\n'
            '  """Docstring"""\n'
            '  try:\n'
            '    return True\n'
            '\n'
            'def method2():\n'
            '  """Docstring"""\n'
            '  try:\n'
            '    return False\n'
        )
        old_hash1 = hasher.hash('def method1():')
        old_hash2 = hasher.hash('def method2():')
        hash_to_content = {
            old_hash1: old_content,
            old_hash2: old_content
        }

        updated = format_tracker._process_file(
            temp_dir,
            "test.py",
            hash_to_content,
            tracking
        )

        assert updated

        # Verify counts
        hashes = tracking.get_ai_hashes_for_file("test.py")

        docstring_hash = hasher.hash('    """Docstring"""')
        try_hash = hasher.hash('    try:')

        # Both appear twice in the formatted file
        assert hashes[docstring_hash] == 2
        assert hashes[try_hash] == 2
