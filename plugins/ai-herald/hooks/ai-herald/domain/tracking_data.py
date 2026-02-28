"""Tracking data domain model."""

from typing import Dict, List, Optional
from domain.line_hasher import LineHasher


class TrackingData:
    """Aggregate root representing AI contribution tracking state.

    Manages the state of which lines are AI-authored across all tracked files
    in a git branch. This is the main domain object that gets persisted to
    the tracking JSON file.
    """

    def __init__(self, branch: str):
        """Initialize tracking data for a branch.

        Args:
            branch: Git branch name
        """
        self.branch = branch
        self.merge_base: Optional[str] = None
        self.ai_line_hashes: Dict[str, Dict[str, int]] = {}
        self.ai_removed_line_hashes: Dict[str, Dict[str, int]] = {}
        self.files_tracked: List[str] = []
        self.stats: Optional[Dict] = None
        self.last_updated: Optional[str] = None
        self.pending_inject_head: Optional[str] = None

    def add_ai_lines(self, file_path: str, lines: List[str], hasher: LineHasher) -> None:
        """Add AI-authored lines to tracking with occurrence counts.

        Increments the count for each line hash. Duplicate lines in the input
        list will increment the count multiple times.

        Args:
            file_path: Relative path from git root
            lines: Lines to mark as AI-authored (may contain duplicates)
            hasher: LineHasher instance for computing hashes
        """
        if file_path not in self.ai_line_hashes:
            self.ai_line_hashes[file_path] = {}

        for line in lines:
            normalized = hasher.normalize(line)
            if normalized:  # Skip empty lines
                line_hash = hasher.hash(normalized, pre_normalized=True)
                if line_hash not in self.ai_line_hashes[file_path]:
                    self.ai_line_hashes[file_path][line_hash] = 0
                self.ai_line_hashes[file_path][line_hash] += 1

    def add_ai_line_hash(self, file_path: str, line_hash: str, count: int = 1) -> None:
        """Add a single AI line hash to tracking with occurrence count.

        Helper method for adding pre-computed hashes (e.g., from format tracker).
        Increments the count by the specified amount.

        Args:
            file_path: Relative path from git root
            line_hash: Pre-computed line hash to add
            count: Number of occurrences to add (default: 1)
        """
        if file_path not in self.ai_line_hashes:
            self.ai_line_hashes[file_path] = {}
        if line_hash not in self.ai_line_hashes[file_path]:
            self.ai_line_hashes[file_path][line_hash] = 0
        self.ai_line_hashes[file_path][line_hash] += count

    def remove_ai_lines(self, file_path: str, lines: List[str], hasher: LineHasher) -> None:
        """Remove AI-authored lines from tracking by decrementing counts.

        Used when lines are deleted or modified by the user. Decrements the count
        for each occurrence. If count reaches 0, the hash is removed from tracking.

        Args:
            file_path: Relative path from git root
            lines: Lines to unmark as AI-authored (may contain duplicates)
            hasher: LineHasher instance for computing hashes
        """
        if file_path not in self.ai_line_hashes:
            return

        for line in lines:
            normalized = hasher.normalize(line)
            if normalized:
                line_hash = hasher.hash(normalized, pre_normalized=True)
                if line_hash in self.ai_line_hashes[file_path]:
                    self.ai_line_hashes[file_path][line_hash] -= 1
                    if self.ai_line_hashes[file_path][line_hash] <= 0:
                        del self.ai_line_hashes[file_path][line_hash]

    def track_file(self, file_path: str) -> None:
        """Add file to tracked files list if not already tracked.

        Args:
            file_path: Relative path from git root
        """
        if file_path not in self.files_tracked:
            self.files_tracked.append(file_path)

    def is_tracked(self, file_path: str) -> bool:
        """Check if file is being tracked.

        Args:
            file_path: Relative path from git root

        Returns:
            True if file is tracked
        """
        return file_path in self.files_tracked

    def get_ai_hashes_for_file(self, file_path: str) -> Dict[str, int]:
        """Get dict of AI line hashes with occurrence counts for a specific file.

        Args:
            file_path: Relative path from git root

        Returns:
            Dict mapping line hash to occurrence count (empty dict if file not tracked)
        """
        return self.ai_line_hashes.get(file_path, {}).copy()

    def track_ai_removals(self, file_path: str, lines: List[str], hasher: LineHasher) -> None:
        """Track lines removed by AI with occurrence counts.

        Records that AI performed the removal action, separate from
        who originally authored the line. Increments count for each occurrence.

        Args:
            file_path: Relative path from git root
            lines: Lines that AI removed (may contain duplicates)
            hasher: LineHasher instance
        """
        if file_path not in self.ai_removed_line_hashes:
            self.ai_removed_line_hashes[file_path] = {}

        for line in lines:
            normalized = hasher.normalize(line)
            if normalized:
                line_hash = hasher.hash(normalized, pre_normalized=True)
                if line_hash not in self.ai_removed_line_hashes[file_path]:
                    self.ai_removed_line_hashes[file_path][line_hash] = 0
                self.ai_removed_line_hashes[file_path][line_hash] += 1

    def get_ai_removed_hashes_for_file(self, file_path: str) -> Dict[str, int]:
        """Get dict of AI-removed line hashes with occurrence counts for a specific file.

        Args:
            file_path: Relative path from git root

        Returns:
            Dict mapping line hash to occurrence count (empty dict if file not tracked)
        """
        return self.ai_removed_line_hashes.get(file_path, {}).copy()
