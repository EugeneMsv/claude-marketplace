"""Tests for FormatSnapshotService."""

import sys
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.format_snapshot_service import FormatSnapshotService
from domain.line_hasher import LineHasher
from domain.tracking_data import TrackingData
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def logger():
    return logging.getLogger("test")


def _make_service(git_root: Path, branch: str = "feature/test", logger=None):
    """Build a FormatSnapshotService wired to a temp git_root."""
    if logger is None:
        logger = logging.getLogger("test")

    git_repo = MagicMock()
    git_repo.get_root.return_value = git_root
    git_repo.get_current_branch.return_value = branch
    git_repo.sanitize_branch_name = lambda branch: branch.replace('/', '-').replace('\\', '-')

    config = MagicMock()
    hasher = LineHasher()

    return FormatSnapshotService(git_repo, config, hasher, logger)


class TestCapturePreFormat:
    """Tests for capture_pre_format(pid)."""

    def test_returns_none_when_no_tracking_data(self, temp_dir):
        """Given no tracking file, returns None without error."""
        (temp_dir / ".claude").mkdir()
        service = _make_service(temp_dir)

        result = service.capture_pre_format(pid=1234)

        assert result is None

    def test_returns_none_when_tracking_has_no_files(self, temp_dir):
        """Given tracking data with no tracked files, returns None."""
        (temp_dir / ".claude").mkdir()
        service = _make_service(temp_dir)

        sanitized = "feature/test".replace('/', '-').replace('\\', '-')
        tracking_repo = TrackingRepository(temp_dir, sanitized)
        tracking = TrackingData("feature/test")
        tracking_repo.save(tracking)

        result = service.capture_pre_format(pid=1234)

        assert result is None

    def test_creates_snapshot_file_when_files_tracked(self, temp_dir):
        """Given tracking data with tracked files, creates snapshot file."""
        (temp_dir / ".claude").mkdir()
        service = _make_service(temp_dir)

        # Create a tracked file with content
        test_file = temp_dir / "app.py"
        test_file.write_text("def foo():\n    pass\n")

        # Create tracking data referencing the file
        hasher = LineHasher()
        sanitized = "feature/test".replace('/', '-').replace('\\', '-')
        tracking_repo = TrackingRepository(temp_dir, sanitized)
        tracking = TrackingData("feature/test")
        tracking.track_file("app.py")
        tracking.add_ai_lines("app.py", ["def foo():", "    pass"], hasher)
        tracking_repo.save(tracking)

        result = service.capture_pre_format(pid=9999)

        assert result is not None
        assert Path(result).exists()
        assert "9999.json" in result

    def test_returns_none_when_no_branch(self, temp_dir):
        """Given git_repo returns no branch, returns None."""
        git_repo = MagicMock()
        git_repo.get_root.return_value = temp_dir
        git_repo.get_current_branch.return_value = None
        service = FormatSnapshotService(git_repo, MagicMock(), LineHasher(), logging.getLogger("test"))

        result = service.capture_pre_format(pid=1)

        assert result is None

    def test_returns_none_when_no_git_root(self, temp_dir):
        """Given git_repo returns no root, returns None."""
        git_repo = MagicMock()
        git_repo.get_root.return_value = None
        git_repo.get_current_branch.return_value = "feature/test"
        service = FormatSnapshotService(git_repo, MagicMock(), LineHasher(), logging.getLogger("test"))

        result = service.capture_pre_format(pid=1)

        assert result is None
