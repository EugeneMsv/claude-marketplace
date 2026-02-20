"""Pre-write file content snapshot repository."""

import hashlib
from pathlib import Path


class WriteSnapshotRepository:
    """Stores file content snapshots before Write tool overwrites them.

    Pre-write snapshots are saved by the PreToolUse Write hook and consumed
    (read + deleted) by the PostToolUse capture hook, bridging the two hook
    invocations so that AI-removed lines can be correctly attributed.

    Snapshots are stored in {git_root}/.claude/write-snapshots/ with filenames
    derived from the sha256 of the absolute file path (first 16 hex chars).
    """

    def __init__(self, git_root: Path):
        """Initialize with the git repository root.

        Args:
            git_root: Root directory of the git repository. May be None —
                      in that case save/load_and_delete are safe no-ops.
        """
        self._dir = git_root / '.claude' / 'write-snapshots' if git_root else None

    def save(self, abs_file_path: str, content: str) -> bool:
        """Snapshot file content before a Write tool overwrites it.

        Args:
            abs_file_path: Absolute path to the file about to be written.
            content: Current (pre-write) content of the file. Pass '' for new files.

        Returns:
            True if the snapshot was saved successfully, False otherwise.
        """
        if not self._dir:
            return False

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = self._snapshot_path(abs_file_path)
            temp_path = snapshot_path.with_suffix('.tmp')
            temp_path.write_text(content, encoding='utf-8')
            temp_path.replace(snapshot_path)
            return True
        except OSError:
            return False

    def load_and_delete(self, abs_file_path: str) -> str:
        """Read and remove the snapshot for the given file path.

        Called by the PostToolUse capture hook to retrieve the pre-write content.
        Deletes the snapshot after reading to avoid stale entries.

        Args:
            abs_file_path: Absolute path to the file that was written.

        Returns:
            Pre-write file content, or '' if no snapshot exists.
        """
        if not self._dir:
            return ''

        snapshot_path = self._snapshot_path(abs_file_path)
        if not snapshot_path.exists():
            return ''

        try:
            content = snapshot_path.read_text(encoding='utf-8')
            snapshot_path.unlink()
            return content
        except OSError:
            return ''

    def _snapshot_path(self, abs_file_path: str) -> Path:
        key = hashlib.sha256(abs_file_path.encode('utf-8')).hexdigest()[:16]
        return self._dir / f'{key}.txt'
