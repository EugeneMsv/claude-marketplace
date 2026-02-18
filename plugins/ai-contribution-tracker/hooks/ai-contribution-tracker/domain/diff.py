"""Git diff domain models."""

from typing import List, Dict, Optional


class DiffFile:
    """Represents changes to a single file in a git diff.

    Immutable value object containing the added and removed lines
    for a specific file.
    """

    def __init__(self, file_path: str, added_lines: List[str], removed_lines: List[str]):
        """Initialize DiffFile.

        Args:
            file_path: Relative path from git root
            added_lines: Lines added in this diff (without + prefix)
            removed_lines: Lines removed in this diff (without - prefix)
        """
        self._file_path = file_path
        self._added_lines = added_lines.copy()
        self._removed_lines = removed_lines.copy()

    @property
    def file_path(self) -> str:
        """Get file path."""
        return self._file_path

    @property
    def added_lines(self) -> List[str]:
        """Get added lines (copy to maintain immutability)."""
        return self._added_lines.copy()

    @property
    def removed_lines(self) -> List[str]:
        """Get removed lines (copy to maintain immutability)."""
        return self._removed_lines.copy()

    def get_added_count(self) -> int:
        """Get count of added lines."""
        return len(self._added_lines)

    def get_removed_count(self) -> int:
        """Get count of removed lines."""
        return len(self._removed_lines)


class Diff:
    """Represents a git diff result across multiple files.

    Immutable collection of file diffs, typically created from
    the output of `git diff`.
    """

    def __init__(self, merge_base: str, files: Dict[str, DiffFile]):
        """Initialize Diff.

        Args:
            merge_base: Commit hash this diff is relative to
            files: Dictionary mapping file paths to their DiffFile objects
        """
        self._merge_base = merge_base
        self._files = files.copy()

    @property
    def merge_base(self) -> str:
        """Get merge base commit hash."""
        return self._merge_base

    def get_changed_files(self) -> List[str]:
        """Get list of all changed file paths."""
        return list(self._files.keys())

    def get_file_diff(self, file_path: str) -> Optional[DiffFile]:
        """Get diff for a specific file.

        Args:
            file_path: Relative file path from git root

        Returns:
            DiffFile object if file has changes, None otherwise
        """
        return self._files.get(file_path)

    def has_changes(self) -> bool:
        """Check if this diff contains any changes."""
        return len(self._files) > 0

    @staticmethod
    def from_git_output(merge_base: str, output: str) -> 'Diff':
        """Parse git diff output into a Diff object.

        Args:
            merge_base: Commit hash this diff is relative to
            output: Raw output from `git diff --unified=0`

        Returns:
            Diff object containing all file changes
        """
        files = {}
        current_file = None
        current_added = []
        current_removed = []

        for line in output.splitlines():
            # Track current file from "+++ b/filepath" headers
            if line.startswith('+++ b/'):
                # Save previous file if exists
                if current_file:
                    files[current_file] = DiffFile(current_file, current_added, current_removed)

                # Start new file
                current_file = line[6:]  # Strip "+++ b/" prefix
                current_added = []
                current_removed = []

            # Lines starting with + (but not +++) are added lines
            elif line.startswith('+') and not line.startswith('+++'):
                if current_file:
                    current_added.append(line[1:])  # Strip + prefix

            # Lines starting with - (but not ---) are removed lines
            elif line.startswith('-') and not line.startswith('---'):
                if current_file:
                    current_removed.append(line[1:])  # Strip - prefix

        # Save last file if exists
        if current_file:
            files[current_file] = DiffFile(current_file, current_added, current_removed)

        return Diff(merge_base, files)
