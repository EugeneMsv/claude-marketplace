"""Tests for DeletionTrackerService."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.deletion_tracker_service import DeletionTrackerService
from domain.tracking_data import TrackingData
from infrastructure.tracking_repository import TrackingRepository


def _make_service(git_root, branch, git_deleted_files):
    """Build a DeletionTrackerService with mocked git and tracking."""
    git_repo = MagicMock()
    git_repo.get_root.return_value = git_root
    git_repo.get_current_branch.return_value = branch

    logger = MagicMock()

    service = DeletionTrackerService(git_repo, MagicMock(), logger)

    # Patch _get_git_deleted_files to return our fixture set
    service._get_git_deleted_files = MagicMock(return_value=set(git_deleted_files))

    return service


class TestProcess:
    """Tests for DeletionTrackerService.process()."""

    def test_single_file_marked_ai_deleted(self, tmp_path):
        """Given target file.py in git-deleted, marks it as AI-deleted."""
        service = _make_service(tmp_path, "feature-branch", ["file.py"])

        matched = service.process({"file.py"})

        assert matched == {"file.py"}
        tracking_repo = TrackingRepository(tmp_path, "feature-branch")
        tracking = tracking_repo.load()
        assert tracking is not None
        assert "file.py" in tracking.ai_deleted_files

    def test_directory_deletion_marks_nested_files(self, tmp_path):
        """Given directory target and nested files in git-deleted, all are marked."""
        git_deleted = [
            "src/old/components/Button.tsx",
            "src/old/components/forms/Input.tsx",
            "src/old/components/forms/validation/rules.ts",
            "src/old/components/utils/helpers/format.ts",
        ]
        service = _make_service(tmp_path, "feature-branch", git_deleted)

        matched = service.process({"src/old/components/"})

        assert matched == set(git_deleted)
        tracking_repo = TrackingRepository(tmp_path, "feature-branch")
        tracking = tracking_repo.load()
        for f in git_deleted:
            assert f in tracking.ai_deleted_files

    def test_directory_deletion_only_matches_inside_prefix(self, tmp_path):
        """Given directory target, only files under that prefix are matched."""
        git_deleted = [
            "src/old/file.py",
            "src/other/file.py",  # not under src/old/
        ]
        service = _make_service(tmp_path, "feature-branch", git_deleted)

        matched = service.process({"src/old/"})

        assert matched == {"src/old/file.py"}

    def test_multiple_targets_some_git_tracked(self, tmp_path):
        """Given multiple targets where only one is git-tracked, only that one is marked."""
        service = _make_service(tmp_path, "feature-branch", ["a.py"])

        matched = service.process({"a.py", "b.py"})

        assert matched == {"a.py"}

    def test_empty_targets_returns_empty(self, tmp_path):
        """Given empty targets set, returns empty and skips git query."""
        service = _make_service(tmp_path, "feature-branch", [])

        matched = service.process(set())

        assert matched == set()
        service._get_git_deleted_files.assert_not_called()

    def test_empty_git_deleted_returns_empty(self, tmp_path):
        """Given targets but no git-tracked deleted files, returns empty."""
        service = _make_service(tmp_path, "feature-branch", [])

        matched = service.process({"file.py"})

        assert matched == set()

    def test_absolute_path_normalized_to_git_relative(self, tmp_path):
        """Given absolute path target, strips git root and matches correctly."""
        service = _make_service(tmp_path, "feature-branch", ["src/old.py"])

        matched = service.process({str(tmp_path / "src/old.py")})

        assert matched == {"src/old.py"}

    def test_dot_slash_prefix_stripped(self, tmp_path):
        """Given ./src/file.py target, strips ./ and matches correctly."""
        service = _make_service(tmp_path, "feature-branch", ["src/file.py"])

        matched = service.process({"./src/file.py"})

        assert matched == {"src/file.py"}

    def test_existing_tracking_data_preserved(self, tmp_path):
        """Given existing tracking data, new deletion is appended without replacing existing data."""
        tracking = TrackingData("feature-branch")
        tracking.files_tracked = ["existing.py"]
        TrackingRepository(tmp_path, "feature-branch").save(tracking)

        service = _make_service(tmp_path, "feature-branch", ["deleted.py"])
        service.process({"deleted.py"})

        loaded = TrackingRepository(tmp_path, "feature-branch").load()
        assert "existing.py" in loaded.files_tracked
        assert "deleted.py" in loaded.ai_deleted_files

    def test_no_git_root_returns_empty(self):
        """Given no git root, returns empty set."""
        git_repo = MagicMock()
        git_repo.get_root.return_value = None
        service = DeletionTrackerService(git_repo, MagicMock(), MagicMock())

        matched = service.process({"file.py"})

        assert matched == set()


class TestNormalizePath:
    """Tests for _normalize_path static method."""

    @pytest.mark.parametrize("raw, git_root, expected", [
        ("file.py",         "/repo",          "file.py"),
        ("./file.py",       "/repo",          "file.py"),
        ("src/old/",        "/repo",          "src/old"),
        ("./src/old/",      "/repo",          "src/old"),
        ("/repo/src/old.py", "/repo",         "src/old.py"),
    ])
    def test_normalize_path(self, raw, git_root, expected):
        """Given raw path token, normalizes to git-relative form."""
        result = DeletionTrackerService._normalize_path(raw, Path(git_root))
        assert result == expected
