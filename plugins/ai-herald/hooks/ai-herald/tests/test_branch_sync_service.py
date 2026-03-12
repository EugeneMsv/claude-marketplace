"""Tests for BranchSyncService."""

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.branch_sync_service import BranchSyncService
from domain.tracking_data import TrackingData


def _make_service(
    branch: Optional[str] = "feature/test",
    git_root: Optional[Path] = Path("/repo"),
    merge_base: Optional[str] = "abc123def456",
):
    """Build a BranchSyncService with mocked dependencies."""
    git_repo = MagicMock()
    git_repo.get_current_branch.return_value = branch
    git_repo.get_root.return_value = git_root
    git_repo.get_merge_base.return_value = merge_base

    config = MagicMock()
    config.base_branches = ["main"]
    logger = MagicMock()

    service = BranchSyncService(git_repo, config, logger)
    return service, git_repo, config, logger


class TestBranchSyncService:

    def test_updates_merge_base_and_saves(self):
        """When tracking file exists, merge_base is recalculated and persisted."""
        service, git_repo, config, _ = _make_service(merge_base="newbase123")
        tracking = TrackingData("feature/test")
        tracking.merge_base = "oldbase456"

        with patch("services.branch_sync_service.TrackingRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.load.return_value = tracking
            repo_instance.save.return_value = True

            result = service.handle()

        assert result is True
        assert tracking.merge_base == "newbase123"
        repo_instance.save.assert_called_once_with(tracking)
        # last_updated should have been refreshed
        assert tracking.last_updated is not None

    def test_skips_when_no_tracking_file(self):
        """Returns False and does not call save when tracking file is missing."""
        service, _, _, _ = _make_service()

        with patch("services.branch_sync_service.TrackingRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.load.return_value = None

            result = service.handle()

        assert result is False
        repo_instance.save.assert_not_called()

    def test_skips_when_get_merge_base_returns_none(self):
        """Returns False and does not save when git cannot find a merge base."""
        service, git_repo, _, _ = _make_service(merge_base=None)
        tracking = TrackingData("feature/test")
        tracking.merge_base = "oldbase"

        with patch("services.branch_sync_service.TrackingRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.load.return_value = tracking

            result = service.handle()

        assert result is False
        repo_instance.save.assert_not_called()
        # merge_base must not be overwritten with None
        assert tracking.merge_base == "oldbase"

    def test_skips_when_no_branch(self):
        """Returns False immediately when current branch cannot be determined."""
        service, git_repo, _, _ = _make_service(branch=None)

        with patch("services.branch_sync_service.TrackingRepository") as MockRepo:
            result = service.handle()

        assert result is False
        MockRepo.assert_not_called()
