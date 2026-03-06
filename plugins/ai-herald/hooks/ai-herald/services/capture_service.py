"""Capture service for AI contribution tracking."""

from collections import Counter
from logging import Logger
from pathlib import Path
from typing import Dict, List
from domain.ignored_files_detector import IgnoredFilesDetector
from domain.line_hasher import LineHasher
from domain.tracking_data import TrackingData
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository
from infrastructure.write_snapshot_repository import WriteSnapshotRepository


class CaptureService:
    """Service coordinating the capture hook workflow.

    Processes Write/Edit tool use events to track AI-authored lines.
    Works in two phases for Write operations:
      1. store_pre_write_snapshot() — called by PreToolUse Write hook, captures
         existing file content before the overwrite.
      2. process_write() — called by PostToolUse Write hook, reads the snapshot
         to compute added/removed lines correctly.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        hasher: LineHasher,
        logger: Logger,
        write_snapshot_repo: WriteSnapshotRepository,
        ignored_files_detector: IgnoredFilesDetector
    ):
        """Initialize capture service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            hasher: LineHasher for computing line hashes
            logger: Logger instance with hook context
            write_snapshot_repo: Repository for storing pre-write file snapshots
            ignored_files_detector: Detector for ignored files (skip tracking)
        """
        self._git_repo = git_repo
        self._config = config
        self._hasher = hasher
        self._logger = logger
        self._write_snapshot_repo = write_snapshot_repo
        self._ignored_files_detector = ignored_files_detector

    def store_pre_write_snapshot(self, file_path: str) -> None:
        """Snapshot existing file content before a Write tool overwrites it.

        Called by the PreToolUse Write hook. Reads the file from disk and saves
        its content to the snapshot repository so that process_write() can later
        compute what lines were removed.

        Args:
            file_path: Absolute path to the file about to be written.
        """
        if not file_path:
            return

        try:
            content = Path(file_path).read_text(encoding='utf-8')
        except (FileNotFoundError, OSError):
            content = ''

        self._write_snapshot_repo.save(file_path, content)

    def process_write(self, tool_input: Dict) -> bool:
        """Process a Write tool use event.

        Reads the pre-write snapshot (saved by store_pre_write_snapshot before
        the Write ran) to determine which lines were removed. For new files the
        snapshot returns '', so all lines are recorded as AI-added.

        Args:
            tool_input: Tool input dictionary containing file_path and content

        Returns:
            True if processing succeeded
        """
        file_path = tool_input.get('file_path', '')
        new_content = tool_input.get('content', '')
        existing_content = self._write_snapshot_repo.load_and_delete(file_path)
        added_lines = self._diff_lines(existing_content, new_content)
        removed_lines = self._diff_lines(new_content, existing_content)
        return self._process(file_path, added_lines, removed_lines)

    def process_edit(self, tool_input: Dict) -> bool:
        """Process an Edit tool use event.

        Args:
            tool_input: Tool input dictionary containing file_path, old_string, new_string

        Returns:
            True if processing succeeded
        """
        old_string = tool_input.get('old_string', '')
        new_string = tool_input.get('new_string', '')
        added_lines = self._diff_lines(old_string, new_string)
        removed_lines = self._diff_lines(new_string, old_string)
        return self._process(tool_input.get('file_path', ''), added_lines, removed_lines)

    def _process(self, file_path_abs: str, added_lines: List[str], removed_lines: List[str]) -> bool:
        """Shared tracking logic: resolve path, load tracking, update and save.

        Args:
            file_path_abs: Absolute path to the file being written/edited
            added_lines: Lines added by the operation
            removed_lines: Lines removed by the operation

        Returns:
            True if tracking was saved successfully
        """
        if not file_path_abs:
            return False

        git_root = self._git_repo.get_root()
        if not git_root:
            return False

        try:
            file_path = str(Path(file_path_abs).relative_to(git_root))
        except ValueError:
            # File outside git root
            return False

        self._logger.info(f"Processing on {file_path}")

        if self._ignored_files_detector.is_ignored(file_path):
            self._logger.info(f"Ignored file, skipping: {file_path}")
            return False

        if not self._config.should_track_file(Path(file_path)):
            ext = Path(file_path).suffix.lower()
            self._logger.info(f"Extension {ext} not tracked, skipping")
            return False

        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return False

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)

        self._logger.info(f"Tracking file: {tracking_repo.tracking_path}")

        tracking = tracking_repo.load()
        if not tracking:
            tracking = TrackingData(branch)

        self._logger.info(f"Added {len(added_lines)} lines, removed {len(removed_lines)} lines")

        tracking.add_ai_lines(file_path, added_lines, self._hasher)
        tracking.track_ai_removals(file_path, removed_lines, self._hasher)
        tracking.track_file(file_path)

        success = tracking_repo.save(tracking)

        if success:
            self._logger.info("Tracking file updated successfully")
        else:
            self._logger.warning("Failed to save tracking file")

        return success

    @staticmethod
    def _diff_lines(old_content: str, new_content: str) -> List[str]:
        """Extract lines present in new but not in old, including duplicates.

        Uses Counter to properly handle duplicate lines. If a line appears N times
        in new_content and M times in old_content, it will be captured (N-M) times.

        Args:
            old_content: Old content string
            new_content: New content string

        Returns:
            List of added lines (includes duplicates)
        """
        old_lines = Counter(old_content.splitlines())
        new_lines = Counter(new_content.splitlines())

        # Subtract counts: new - old gives us the added occurrences
        added_counts = new_lines - old_lines

        # Convert Counter back to list with proper multiplicity
        return list(added_counts.elements())
