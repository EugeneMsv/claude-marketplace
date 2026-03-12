"""Housekeeping service for AI contribution tracking."""

import json
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import List, Tuple
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration


class HousekeepingResult:
    """Result of housekeeping cleanup operation."""

    def __init__(self, files_deleted: int, files_skipped: int, files_errored: int):
        """Initialize housekeeping result.

        Args:
            files_deleted: Number of stale files successfully deleted
            files_skipped: Number of files skipped (not stale or current branch)
            files_errored: Number of files that encountered errors
        """
        self.files_deleted = files_deleted
        self.files_skipped = files_skipped
        self.files_errored = files_errored


class HousekeepingService:
    """Service for cleaning up stale tracking files.

    Removes tracking files for branches that no longer exist locally
    and are older than the configured threshold.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        logger: Logger
    ):
        """Initialize housekeeping service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._logger = logger

    def cleanup_stale_tracking_files(self) -> HousekeepingResult:
        """Clean up tracking files for deleted/merged branches.

        Finds tracking files, excludes current branch, selects oldest files up to
        maxFilesPerRun, checks if branches exist locally, and deletes files for
        branches that don't exist locally and are older than staleDaysThreshold.

        Returns:
            HousekeepingResult with counts of deleted, skipped, and errored files
        """
        files_deleted = 0
        files_skipped = 0
        files_errored = 0

        # Get git root and current branch
        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("Not in git repository, skipping housekeeping")
            return HousekeepingResult(files_deleted, files_skipped, files_errored)

        current_branch = self._git_repo.get_current_branch()
        if not current_branch:
            self._logger.warning("Could not determine current branch, skipping housekeeping")
            return HousekeepingResult(files_deleted, files_skipped, files_errored)

        # Find all tracking files
        herald_dir = git_root / '.claude' / 'herald'
        if not herald_dir.exists():
            return HousekeepingResult(files_deleted, files_skipped, files_errored)

        tracking_files = list(herald_dir.glob('*.json'))
        if not tracking_files:
            return HousekeepingResult(files_deleted, files_skipped, files_errored)

        # Parse and filter candidates
        candidates = self._parse_tracking_files(tracking_files, current_branch)

        # Sort by oldest first and limit to maxFilesPerRun
        candidates.sort(key=lambda x: x[1])  # Sort by last_updated
        max_files = self._config.housekeeping_max_files
        candidates = candidates[:max_files]

        # Process each candidate
        stale_threshold_days = self._config.housekeeping_stale_days
        for file_path, last_updated, branch in candidates:
            try:
                # Check if branch exists locally
                if self._git_repo.branch_exists_locally(branch):
                    self._logger.debug(f"Branch '{branch}' exists locally, skipping")
                    files_skipped += 1
                    continue

                # Calculate age in days
                age_days = (datetime.now() - last_updated).days

                # Delete if older than threshold
                if age_days >= stale_threshold_days:
                    file_path.unlink()
                    files_deleted += 1
                    self._logger.info(f"Deleted stale tracking file: {file_path.name} (branch: {branch}, age: {age_days} days)")
                else:
                    self._logger.debug(f"File not old enough: {file_path.name} (age: {age_days} days)")
                    files_skipped += 1

            except OSError as e:
                self._logger.error(f"Failed to delete {file_path.name}: {e}")
                files_errored += 1
            except Exception as e:
                self._logger.error(f"Unexpected error processing {file_path.name}: {e}")
                files_errored += 1

        return HousekeepingResult(files_deleted, files_skipped, files_errored)

    def _parse_tracking_files(
        self,
        tracking_files: List[Path],
        current_branch: str
    ) -> List[Tuple[Path, datetime, str]]:
        """Parse tracking files and extract metadata.

        Args:
            tracking_files: List of tracking file paths
            current_branch: Current branch name (to exclude)

        Returns:
            List of tuples: (file_path, last_updated, branch_name)
        """
        candidates = []

        for file_path in tracking_files:
            try:
                # Extract branch name from filename
                filename = file_path.name
                if not filename.endswith('.json'):
                    continue

                sanitized_branch = filename[:-len('.json')]
                # Reverse sanitization: - back to /
                # Note: This is a simple heuristic and may not be perfect for all cases
                branch = sanitized_branch.replace('-', '/')

                # Exclude current branch
                if branch == current_branch or sanitized_branch == self._git_repo.sanitize_branch_name(current_branch):
                    self._logger.debug(f"Excluding current branch: {file_path.name}")
                    continue

                # Parse file to get last_updated
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Get last_updated from file, fallback to file mtime
                last_updated_str = data.get('last_updated')
                if last_updated_str:
                    last_updated = datetime.fromisoformat(last_updated_str)
                else:
                    # Fallback to file modification time
                    last_updated = datetime.fromtimestamp(file_path.stat().st_mtime)
                    self._logger.debug(f"Using file mtime for {file_path.name}")

                # Use branch name from file content if available (more accurate)
                if 'branch' in data:
                    branch = data['branch']

                candidates.append((file_path, last_updated, branch))

            except json.JSONDecodeError as e:
                self._logger.warning(f"Skipping corrupted file {file_path.name}: {e}")
            except IOError as e:
                self._logger.warning(f"Skipping unreadable file {file_path.name}: {e}")
            except Exception as e:
                self._logger.warning(f"Skipping file {file_path.name} due to error: {e}")

        return candidates
