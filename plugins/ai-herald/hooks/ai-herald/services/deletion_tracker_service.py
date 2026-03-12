"""Deletion tracker service for AI contribution tracking."""

import subprocess
from logging import Logger
from pathlib import Path
from typing import Set

from domain.tracking_data import TrackingData
from infrastructure.configuration import Configuration
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository


class DeletionTrackerService:
    """PostToolUse Bash service — detects file deletions and marks them as AI-authored.

    After a Bash command runs, this service:
    1. Parses the command for rm/git rm/unlink patterns.
    2. Queries git for currently uncommitted deleted files.
    3. Cross-references command targets against the git-deleted list using prefix matching.
    4. Marks matched files as AI-deleted in tracking data.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        logger: Logger,
    ):
        """Initialize deletion tracker service.

        Args:
            git_repo: GitRepository for git operations and path resolution
            config: Configuration settings
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._logger = logger

    def process(self, targets: Set[str]) -> Set[str]:
        """Mark AI-deleted files in tracking from pre-extracted deletion targets.

        Args:
            targets: Raw path tokens extracted from the bash command

        Returns:
            Set of git-relative file paths that were marked as AI-deleted
        """
        self._logger.info(f"Processing {len(targets)} deletion target(s)")
        if not targets:
            return set()

        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("Could not determine git root; skipping deletion tracking")
            return set()

        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch; skipping deletion tracking")
            return set()

        git_deleted = self._get_git_deleted_files()
        if not git_deleted:
            return set()

        matched: Set[str] = set()
        for raw_target in targets:
            normalized = self._normalize_path(raw_target, git_root)
            for deleted_file in git_deleted:
                if deleted_file == normalized or deleted_file.startswith(normalized + "/"):
                    matched.add(deleted_file)

        if not matched:
            self._logger.info("No deletion targets matched git-deleted files, skipping")
            return set()

        sanitized_branch = self._git_repo.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()
        if not tracking:
            tracking = TrackingData(branch)

        for file_path in matched:
            tracking.mark_file_deleted_by_ai(file_path)
            self._logger.info(f"Marked as AI-deleted: {file_path}")

        tracking_repo.save(tracking)
        self._logger.info(f"Deletion tracking complete: {len(matched)} file(s) marked")
        return matched

    def _get_git_deleted_files(self) -> Set[str]:
        """Query git for files deleted but not yet committed.

        Returns:
            Set of git-root-relative paths for all uncommitted deleted files
        """
        try:
            result = subprocess.run(
                ['git', 'diff', '--diff-filter=D', '--name-only', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            lines = result.stdout.strip().splitlines()
            return {line.strip() for line in lines if line.strip()}
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()

    @staticmethod
    def _normalize_path(raw_target: str, git_root: Path) -> str:
        """Normalize a raw command path token to a git-root-relative form.

        Handles:
        - Relative paths: strip leading ./
        - Trailing slashes: strip for directory prefix matching
        - Absolute paths: strip git root prefix

        Args:
            raw_target: Raw path token from the command (e.g. './src/', '/abs/path/file.py')
            git_root: Absolute git root path

        Returns:
            Git-root-relative path without trailing slash
        """
        # Handle absolute paths — strip git root prefix
        if raw_target.startswith('/'):
            try:
                rel = Path(raw_target).relative_to(git_root)
                return str(rel).rstrip('/')
            except ValueError:
                pass  # Not under git root — keep as-is for comparison

        # Strip leading ./ (exact prefix) and trailing /
        normalized = raw_target[2:] if raw_target.startswith('./') else raw_target
        normalized = normalized.rstrip('/')
        return normalized
