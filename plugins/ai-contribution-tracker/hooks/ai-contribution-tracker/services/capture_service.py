"""Capture service for AI contribution tracking."""

from collections import Counter
from logging import Logger
from pathlib import Path
from typing import Dict, List, Tuple
from domain.line_hasher import LineHasher
from domain.tracking_data import TrackingData
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository


class CaptureService:
    """Service coordinating the capture hook workflow.

    Processes Write/Edit tool use events to track AI-authored lines.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        hasher: LineHasher,
        logger: Logger
    ):
        """Initialize capture service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            hasher: LineHasher for computing line hashes
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._hasher = hasher
        self._logger = logger

    def process_tool_use(self, tool_name: str, tool_input: Dict) -> bool:
        """Process a Write or Edit tool use event.

        Args:
            tool_name: Tool name ('Write' or 'Edit')
            tool_input: Tool input dictionary

        Returns:
            True if processing succeeded
        """
        # Only handle Write and Edit
        if tool_name not in ['Write', 'Edit']:
            return False

        # Extract file path
        file_path_abs = tool_input.get('file_path', '')
        if not file_path_abs:
            return False

        # Convert to relative path from git root
        git_root = self._git_repo.get_root()
        if not git_root:
            return False

        try:
            file_path = str(Path(file_path_abs).relative_to(git_root))
        except ValueError:
            # File outside git root
            return False

        self._logger.info(f"Processing {tool_name} on {file_path}")

        # Check if file extension is tracked
        if not self._config.should_track_file(Path(file_path)):
            ext = Path(file_path).suffix.lower()
            self._logger.info(f"Extension {ext} not tracked, skipping")
            return False

        # Get current branch
        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return False

        # Get or create tracking data
        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)

        self._logger.info(f"Tracking file: {tracking_repo.tracking_path}")

        tracking = tracking_repo.load()
        if not tracking:
            tracking = TrackingData(branch)

        # Extract added and removed lines
        added_lines, removed_lines = self._extract_changes(tool_name, tool_input)

        self._logger.info(f"Added {len(added_lines)} lines, removed {len(removed_lines)} lines")

        # Update tracking data
        tracking.add_ai_lines(file_path, added_lines, self._hasher)
        tracking.track_ai_removals(file_path, removed_lines, self._hasher)
        tracking.track_file(file_path)

        # Save tracking data
        success = tracking_repo.save(tracking)

        if success:
            self._logger.info("Tracking file updated successfully")
        else:
            self._logger.warning("Failed to save tracking file")

        return success

    def _extract_changes(self, tool_name: str, tool_input: Dict) -> Tuple[List[str], List[str]]:
        """Extract added and removed lines from tool input.

        Args:
            tool_name: Tool name ('Write' or 'Edit')
            tool_input: Tool input dictionary

        Returns:
            Tuple of (added_lines, removed_lines)
        """
        if tool_name == 'Edit':
            old_string = tool_input.get('old_string', '')
            new_string = tool_input.get('new_string', '')
            added_lines = self._diff_lines(old_string, new_string)
            removed_lines = self._diff_lines(new_string, old_string)
            return added_lines, removed_lines
        else:  # Write
            content = tool_input.get('content', '')
            return content.splitlines(), []

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
