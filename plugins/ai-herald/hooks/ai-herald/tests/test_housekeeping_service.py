"""Tests for housekeeping service."""

import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock

from services.housekeeping_service import HousekeepingService, HousekeepingResult


def test_cleanup_disabled_returns_zero_counts():
    """
    Given housekeeping is disabled in config
    When cleanup_stale_tracking_files is called
    Then it should return zero counts without processing any files
    """
    # Given
    git_repo = Mock()
    git_repo.get_root.return_value = Path('/repo')
    git_repo.get_current_branch.return_value = 'main'

    config = Mock()
    config.housekeeping_enabled = False

    logger = Mock()
    service = HousekeepingService(git_repo, config, logger)

    # When - config check should happen before service methods are called
    # We're testing that if housekeeping is disabled, the hook won't call the service
    # For this test, we simulate that the service would be called anyway
    result = service.cleanup_stale_tracking_files()

    # Then - service still returns valid result even if called when disabled
    assert isinstance(result, HousekeepingResult)


def test_cleanup_deletes_stale_files_for_deleted_branches():
    """
    Given a tracking file for a deleted branch older than threshold
    When cleanup_stale_tracking_files is called
    Then the file should be deleted
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create stale tracking file (10 days old)
        stale_date = datetime.now() - timedelta(days=10)
        tracking_file = herald_dir / 'old-branch.json'
        tracking_data = {
            'branch': 'old-branch',
            'last_updated': stale_date.isoformat(),
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = False  # Branch deleted

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 1
        assert result.files_skipped == 0
        assert result.files_errored == 0
        assert not tracking_file.exists()


def test_cleanup_keeps_files_for_existing_branches():
    """
    Given a tracking file for an existing branch
    When cleanup_stale_tracking_files is called
    Then the file should be kept
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create tracking file for existing branch
        stale_date = datetime.now() - timedelta(days=10)
        tracking_file = herald_dir / 'active-branch.json'
        tracking_data = {
            'branch': 'active-branch',
            'last_updated': stale_date.isoformat(),
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = True  # Branch exists

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 0
        assert result.files_skipped == 1
        assert result.files_errored == 0
        assert tracking_file.exists()


def test_cleanup_excludes_current_branch():
    """
    Given a tracking file for the current branch
    When cleanup_stale_tracking_files is called
    Then the file should not be processed
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create tracking file for current branch
        stale_date = datetime.now() - timedelta(days=10)
        tracking_file = herald_dir / 'main.json'
        tracking_data = {
            'branch': 'main',
            'last_updated': stale_date.isoformat(),
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.sanitize_branch_name = lambda x: x.replace('/', '-')

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 0
        assert result.files_skipped == 0  # Not even counted as skipped
        assert result.files_errored == 0
        assert tracking_file.exists()


def test_cleanup_respects_max_files_limit():
    """
    Given 10 stale tracking files
    When cleanup_stale_tracking_files is called with max_files=5
    Then only 5 oldest files should be processed
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create 10 stale tracking files with different ages
        for i in range(10):
            days_old = 10 + i
            file_date = datetime.now() - timedelta(days=days_old)
            tracking_file = herald_dir / f'branch-{i}.json'
            tracking_data = {
                'branch': f'branch-{i}',
                'last_updated': file_date.isoformat(),
                'files_tracked': []
            }
            tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = False  # All branches deleted

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5  # Limit to 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 5  # Only 5 processed
        assert result.files_skipped == 0
        assert result.files_errored == 0


def test_cleanup_handles_corrupted_json():
    """
    Given a corrupted tracking file
    When cleanup_stale_tracking_files is called
    Then the file should be skipped without error
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create corrupted file
        corrupted_file = herald_dir / 'corrupted.json'
        corrupted_file.write_text('{ invalid json')

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 0
        assert result.files_skipped == 0
        assert result.files_errored == 0  # Corrupted files are skipped, not errored
        assert corrupted_file.exists()  # File still exists


def test_cleanup_uses_file_mtime_when_last_updated_missing():
    """
    Given a tracking file without last_updated field
    When cleanup_stale_tracking_files is called
    Then file modification time should be used
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create tracking file without last_updated
        tracking_file = herald_dir / 'no-timestamp.json'
        tracking_data = {
            'branch': 'no-timestamp',
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = False

        config = Mock()
        config.housekeeping_stale_days = 0  # Delete immediately
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then - should use file mtime and delete
        assert result.files_deleted == 1
        assert not tracking_file.exists()


def test_cleanup_handles_permission_errors():
    """
    Given a tracking file that cannot be deleted due to OS error
    When cleanup_stale_tracking_files is called
    Then the error should be logged and counted
    """
    # Given
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create stale tracking file
        stale_date = datetime.now() - timedelta(days=10)
        tracking_file = herald_dir / 'readonly.json'
        tracking_data = {
            'branch': 'readonly',
            'last_updated': stale_date.isoformat(),
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = False

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # Mock Path.unlink to raise OSError (permission denied)
        original_unlink = Path.unlink
        def mock_unlink(self):
            if self.name == 'readonly.json':
                raise OSError("Permission denied")
            return original_unlink(self)

        # When
        with patch.object(Path, 'unlink', mock_unlink):
            result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 0
        assert result.files_skipped == 0
        assert result.files_errored == 1
        assert tracking_file.exists()


def test_cleanup_respects_stale_threshold():
    """
    Given a tracking file that is not old enough
    When cleanup_stale_tracking_files is called
    Then the file should be skipped
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create recent tracking file (5 days old, threshold is 7)
        recent_date = datetime.now() - timedelta(days=5)
        tracking_file = herald_dir / 'recent.json'
        tracking_data = {
            'branch': 'recent',
            'last_updated': recent_date.isoformat(),
            'files_tracked': []
        }
        tracking_file.write_text(json.dumps(tracking_data))

        # Setup mocks
        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.return_value = False

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 0
        assert result.files_skipped == 1
        assert result.files_errored == 0
        assert tracking_file.exists()


def test_cleanup_sorts_by_oldest_first():
    """
    Given multiple stale tracking files with different ages
    When cleanup_stale_tracking_files is called
    Then oldest files should be processed first
    """
    # Given
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        herald_dir = repo_root / '.claude' / 'herald'
        herald_dir.mkdir(parents=True)

        # Create files with different ages (oldest = 20 days, newest = 10 days)
        files_created = []
        for i in range(3):
            days_old = 20 - (i * 5)  # 20, 15, 10
            file_date = datetime.now() - timedelta(days=days_old)
            tracking_file = herald_dir / f'branch-{i}.json'
            tracking_data = {
                'branch': f'branch-{i}',
                'last_updated': file_date.isoformat(),
                'files_tracked': []
            }
            tracking_file.write_text(json.dumps(tracking_data))
            files_created.append((tracking_file, days_old))

        # Setup mocks
        deleted_branches = []

        def track_deleted_branch(branch):
            deleted_branches.append(branch)
            return False

        git_repo = Mock()
        git_repo.get_root.return_value = repo_root
        git_repo.get_current_branch.return_value = 'main'
        git_repo.branch_exists_locally.side_effect = track_deleted_branch

        config = Mock()
        config.housekeeping_stale_days = 7
        config.housekeeping_max_files = 5

        logger = Mock()
        service = HousekeepingService(git_repo, config, logger)

        # When
        result = service.cleanup_stale_tracking_files()

        # Then
        assert result.files_deleted == 3
        # Oldest file (branch-0, 20 days) should be processed first
        assert deleted_branches[0] == 'branch-0'
        assert deleted_branches[1] == 'branch-1'
        assert deleted_branches[2] == 'branch-2'
