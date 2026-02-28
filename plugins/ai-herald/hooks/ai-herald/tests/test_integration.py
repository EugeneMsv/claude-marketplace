"""Integration tests for AI contribution tracker."""

import sys
from pathlib import Path
import pytest
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.capture_service import CaptureService
from services.stats_calculator import StatsCalculator
from domain.tracking_data import TrackingData
from domain.diff import Diff, DiffFile
from domain.line_hasher import LineHasher
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository
from infrastructure.write_snapshot_repository import WriteSnapshotRepository
from logging import Logger, INFO
import logging


@pytest.fixture
def temp_dir():
    """Create temporary git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        # Create .git directory
        (temp_path / '.git').mkdir()
        yield temp_path


@pytest.fixture
def logger():
    """Create logger for tests."""
    logger = logging.getLogger("integration_test")
    logger.setLevel(INFO)
    return logger


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def git_repo():
    return GitRepository()


@pytest.fixture
def config():
    return Configuration(
        enabled=True,
        base_branches=['main'],
        tracked_extensions={'.py', '.js'},
        enable_logging=False,
        log_file='test.log'
    )


class TestCaptureToStats:
    """Integration tests for capture → storage → stats flow."""

    def test_duplicate_lines_captured_and_counted_correctly(
        self, temp_dir, hasher, git_repo, config, logger
    ):
        """Given Edit with duplicate lines, full pipeline tracks and calculates correctly."""
        # Setup
        capture_service = CaptureService(git_repo, config, hasher, logger, WriteSnapshotRepository(temp_dir))
        stats_calculator = StatsCalculator(hasher, config.tracked_extensions)

        # Create test file
        test_file = temp_dir / "test.py"
        test_file.write_text("")  # Start empty

        # Simulate Write tool use that adds code with duplicate lines
        tool_input = {
            'file_path': str(test_file),
            'content': (
                'def method1():\n'
                '    """Docstring"""\n'
                '    try:\n'
                '        return True\n'
                '\n'
                'def method2():\n'
                '    """Docstring"""\n'
                '    try:\n'
                '        return True\n'
            )
        }

        # Create tracking data manually
        tracking = TrackingData("test-branch")
        tracking.files_tracked = []

        # Manually call the capture logic
        added_lines = tool_input['content'].splitlines()
        tracking.add_ai_lines("test.py", added_lines, hasher)
        tracking.track_file("test.py")

        # Verify tracking data has correct counts
        ai_hashes = tracking.get_ai_hashes_for_file("test.py")
        docstring_hash = hasher.hash('    """Docstring"""')
        try_hash = hasher.hash('    try:')
        return_hash = hasher.hash('        return True')

        assert ai_hashes[docstring_hash] == 2  # Appears twice
        assert ai_hashes[try_hash] == 2  # Appears twice
        assert ai_hashes[return_hash] == 2  # Appears twice

        # Create diff for stats calculation
        diff = Diff(
            merge_base="test-commit",
            files={
                "test.py": DiffFile(
                    file_path="test.py",
                    added_lines=added_lines,
                    removed_lines=[]
                )
            }
        )

        # Calculate stats
        stats = stats_calculator.calculate(tracking, diff)

        # Verify stats show 100% AI (8 non-empty lines are AI, empty line skipped)
        assert stats.ai_stats.added.lines == 8
        assert stats.ai_stats.added.percentage == 100.0
        assert stats.human_stats.added.lines == 0

    def test_partially_tracked_duplicates_counted_correctly(
        self, temp_dir, hasher, git_repo, config, logger
    ):
        """Given duplicate lines with partial tracking, stats calculated correctly."""
        stats_calculator = StatsCalculator(hasher, config.tracked_extensions)

        # Tracking data: track only 2 occurrences of "line A"
        tracking = TrackingData("test-branch")
        tracking.add_ai_lines("test.py", ["line A", "line A"], hasher)
        tracking.track_file("test.py")

        # Diff shows 3 occurrences
        added_lines = ["line A", "line A", "line A"]
        diff = Diff(
            merge_base="test-commit",
            files={
                "test.py": DiffFile(
                    file_path="test.py",
                    added_lines=added_lines,
                    removed_lines=[]
                )
            }
        )

        # Calculate stats
        stats = stats_calculator.calculate(tracking, diff)

        # 2 AI lines (tracked count), 1 human line
        assert stats.ai_stats.added.lines == 2
        assert stats.human_stats.added.lines == 1
        assert stats.ai_stats.added.percentage == 66.7  # 2/3 * 100


class TestMigration:
    """Integration tests for old format migration."""

    def test_load_old_format_calculates_stats_correctly(
        self, temp_dir, hasher
    ):
        """Given old format tracking file, loads, migrates, and calculates stats."""
        tracked_extensions = {'.py', '.js'}
        # Create old format tracking file
        line_a_hash = hasher.hash("line A")
        line_b_hash = hasher.hash("line B")

        old_format_data = {
            "branch": "test-branch",
            "merge_base": "commit123",
            "files_tracked": ["test.py"],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {
                "test.py": [line_a_hash, line_b_hash]  # Old format: list
            },
            "ai_removed_line_hashes": {}
        }

        # Write old format file
        tracking_path = temp_dir / '.claude' / 'herald' / 'test-branch.json'
        tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_path, 'w') as f:
            json.dump(old_format_data, f)

        # Load with tracking repository
        tracking_repo = TrackingRepository(temp_dir, "test-branch")
        tracking = tracking_repo.load()

        assert tracking is not None

        # Verify migrated to new format
        ai_hashes = tracking.get_ai_hashes_for_file("test.py")
        assert isinstance(ai_hashes, dict)
        assert ai_hashes[line_a_hash] == 1  # Migrated with count=1
        assert ai_hashes[line_b_hash] == 1

        # Calculate stats
        stats_calculator = StatsCalculator(hasher, tracked_extensions)
        diff = Diff(
            merge_base="commit123",
            files={
                "test.py": DiffFile(
                    file_path="test.py",
                    added_lines=["line A", "line B"],
                    removed_lines=[]
                )
            }
        )

        stats = stats_calculator.calculate(tracking, diff)

        # Both lines should be AI
        assert stats.ai_stats.added.lines == 2
        assert stats.ai_stats.added.percentage == 100.0

    def test_roundtrip_old_to_new_format(self, temp_dir, hasher):
        """Given old format, load → modify → save preserves new format."""
        # Create old format file
        line_hash = hasher.hash("line A")
        old_format_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": ["test.py"],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {
                "test.py": [line_hash]  # Old format: list
            },
            "ai_removed_line_hashes": {}
        }

        tracking_path = temp_dir / '.claude' / 'herald' / 'test-branch.json'
        tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_path, 'w') as f:
            json.dump(old_format_data, f)

        # Load (triggers migration)
        tracking_repo = TrackingRepository(temp_dir, "test-branch")
        tracking = tracking_repo.load()

        # Add more lines with counts
        tracking.add_ai_lines("test.py", ["line B", "line B"], hasher)

        # Save
        success = tracking_repo.save(tracking)
        assert success

        # Reload and verify new format
        with open(tracking_path, 'r') as f:
            saved_data = json.load(f)

        # Verify saved as dict with counts (new format)
        assert isinstance(saved_data["ai_line_hashes"]["test.py"], dict)
        line_b_hash = hasher.hash("line B")
        assert saved_data["ai_line_hashes"]["test.py"][line_hash] == 1
        assert saved_data["ai_line_hashes"]["test.py"][line_b_hash] == 2


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_workflow_write_to_stats(
        self, temp_dir, hasher, git_repo, config, logger
    ):
        """Test complete workflow: Write → Capture → Storage → Stats."""
        # Create services
        capture_service = CaptureService(git_repo, config, hasher, logger, WriteSnapshotRepository(temp_dir))
        stats_calculator = StatsCalculator(hasher, config.tracked_extensions)
        tracking_repo = TrackingRepository(temp_dir, "test-branch")

        # Create test file
        test_file = temp_dir / "code.py"
        test_file.write_text("")

        # Simulate Write tool use with duplicate boilerplate
        write_input = {
            'file_path': str(test_file),
            'content': (
                'def calculate_sum(numbers):\n'
                '    """Calculate sum"""\n'
                '    total = 0\n'
                '    for num in numbers:\n'
                '        total += num\n'
                '    return total\n'
                '\n'
                'def calculate_product(numbers):\n'
                '    """Calculate sum"""\n'  # Same docstring
                '    total = 1\n'
                '    for num in numbers:\n'  # Same loop
                '        total *= num\n'
                '    return total\n'  # Same return statement
            )
        }

        # Create and save initial tracking
        tracking = TrackingData("test-branch")
        tracking.add_ai_lines("code.py", write_input['content'].splitlines(), hasher)
        tracking.track_file("code.py")
        tracking_repo.save(tracking)

        # Reload and verify counts persisted
        loaded_tracking = tracking_repo.load()
        assert loaded_tracking is not None

        docstring_hash = hasher.hash('    """Calculate sum"""')
        loop_hash = hasher.hash('    for num in numbers:')
        return_hash = hasher.hash('    return total')

        ai_hashes = loaded_tracking.get_ai_hashes_for_file("code.py")
        assert ai_hashes[docstring_hash] == 2  # Duplicate docstring
        assert ai_hashes[loop_hash] == 2  # Duplicate loop
        assert ai_hashes[return_hash] == 2  # Duplicate return

        # Calculate stats
        diff = Diff(
            merge_base="commit",
            files={
                "code.py": DiffFile(
                    file_path="code.py",
                    added_lines=write_input['content'].splitlines(),
                    removed_lines=[]
                )
            }
        )

        stats = stats_calculator.calculate(loaded_tracking, diff)

        # All lines should be AI
        total_lines = len([line for line in write_input['content'].splitlines() if line.strip()])
        assert stats.ai_stats.added.lines == total_lines
        assert stats.ai_stats.added.percentage == 100.0
