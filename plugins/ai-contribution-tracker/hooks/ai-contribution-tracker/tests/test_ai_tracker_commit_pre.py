"""Tests for ai-tracker-commit-pre hook logic."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.tracking_data import TrackingData
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository
from infrastructure.configuration import Configuration
from services.bash_command_detector import BashCommandDetector, DetectedCommand


def _make_detector():
    """Build a detector with no format commands (commit-pre doesn't need them)."""
    config = MagicMock()
    config.format_commands = []
    return BashCommandDetector(config)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_root(temp_dir):
    (temp_dir / ".claude").mkdir()
    return temp_dir


class TestCommitIntentRecording:
    """Tests for the commit intent recording logic."""

    def _run_hook(self, command: str, git_root: Path, tracking: TrackingData, head_hash: str = "abc123"):
        """Helper: simulate the hook's core logic against real objects."""
        branch = "feature-branch"
        sanitized = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized)
        tracking_repo.save(tracking)

        detector = _make_detector()
        if DetectedCommand.GIT_COMMIT not in detector.detect_commands(command):
            return tracking_repo.load()

        loaded = tracking_repo.load()
        if loaded:
            loaded.pending_inject_head = head_hash
            tracking_repo.save(loaded)

        return tracking_repo.load()

    def test_records_head_hash_for_git_commit(self, git_root):
        """Given git commit command, writes pending_inject_head to tracking file."""
        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["file.py"]

        result = self._run_hook("git commit -m 'msg'", git_root, tracking, "abc123")

        assert result is not None
        assert result.pending_inject_head == "abc123"

    def test_records_head_for_chained_commit_push(self, git_root):
        """Given chained git add && git commit && git push, records intent."""
        tracking = TrackingData("feature-branch")

        result = self._run_hook(
            "git add . && git commit -m 'msg' && git push",
            git_root, tracking, "deadbeef"
        )

        assert result.pending_inject_head == "deadbeef"

    def test_skips_amend_command(self, git_root):
        """Given git commit --amend, does not overwrite pending_inject_head."""
        tracking = TrackingData("feature-branch")
        tracking.pending_inject_head = "original"

        result = self._run_hook("git commit --amend --no-edit", git_root, tracking, "newhead")

        assert result.pending_inject_head == "original"

    def test_skips_non_commit_command(self, git_root):
        """Given git push command, does not write pending_inject_head."""
        tracking = TrackingData("feature-branch")

        result = self._run_hook("git push", git_root, tracking, "somehash")

        assert result.pending_inject_head is None

    def test_skips_when_no_tracking_file(self, git_root):
        """Given no tracking file, hook exits without error."""
        branch = "feature-branch"
        sanitized = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized)

        assert tracking_repo.load() is None


class TestBashCommandDetectorIntegration:
    """Verify detector correctly classifies commands the hook encounters."""

    @pytest.mark.parametrize("command,expect_commit,expect_amend", [
        ("git commit -m 'msg'", True, False),
        ("git add . && git commit -m 'msg' && git push", True, False),
        ("git commit --amend --no-edit", False, True),
        ("git push", False, False),
        ("git add .", False, False),
    ])
    def test_command_classification(self, command, expect_commit, expect_amend):
        """Given various commands, detector classifies correctly."""
        detector = _make_detector()
        detected = detector.detect_commands(command)
        assert (DetectedCommand.GIT_COMMIT in detected) == expect_commit
        assert (DetectedCommand.GIT_COMMIT_AMEND in detected) == expect_amend
