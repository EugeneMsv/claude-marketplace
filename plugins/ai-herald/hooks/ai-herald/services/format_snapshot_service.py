"""Format snapshot service for capturing pre-format state."""

from logging import Logger
from pathlib import Path
from typing import Dict, Optional
from domain.format_snapshot import FormatSnapshot
from domain.line_hasher import LineHasher
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository


class FormatSnapshotService:
    """
    Service for capturing file state before formatting.

    This service runs in the PreToolUse hook before formatters execute.
    It creates a temporary snapshot of AI-attributed line content that
    can be compared with post-format state.

    Caller is responsible for routing: only invoke when format_detection_enabled
    and a CODE_FORMATTER command was detected.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        hasher: LineHasher,
        logger: Logger
    ):
        """Initialize format snapshot service.

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

    def capture_pre_format(self, pid: int) -> Optional[str]:
        """
        Capture file state before formatting command runs.

        Args:
            pid: Process ID of the command

        Returns:
            Path to snapshot file if successful, None otherwise
        """
        self._logger.info("Detected format command")

        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return None

        git_root = self._git_repo.get_root()
        if not git_root:
            return None

        sanitized_branch = GitRepository.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)
        tracking = tracking_repo.load()

        if not tracking or not tracking.files_tracked:
            # No files being tracked, nothing to snapshot
            self._logger.info("No tracked files, skipping snapshot")
            return None

        snapshot = FormatSnapshot.create_new(pid, branch)

        for file_path in tracking.files_tracked:
            hash_to_content = self._capture_file_content(
                git_root,
                file_path,
                tracking.get_ai_hashes_for_file(file_path)
            )

            if hash_to_content:
                snapshot.add_file_content(file_path, hash_to_content)

        snapshot_dir = git_root / '.claude' / 'herald' / 'formatting'
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f'{pid}.json'

        try:
            snapshot.save_to_file(str(snapshot_path))
            self._logger.info(f"Saved snapshot to {snapshot_path}")
            return str(snapshot_path)
        except Exception as e:
            self._logger.error(f"Failed to save snapshot: {e}")
            return None

    def _capture_file_content(
        self,
        git_root: Path,
        file_path: str,
        ai_hashes: Dict[str, int]
    ) -> Dict[str, str]:
        """
        Capture content of AI-attributed lines in a file.

        Args:
            git_root: Git repository root
            file_path: Relative path to file
            ai_hashes: Dict mapping AI-attributed line hashes to occurrence counts

        Returns:
            Mapping of hash → line content
        """
        hash_to_content = {}

        if not ai_hashes:
            return hash_to_content

        full_path = git_root / file_path
        if not full_path.exists():
            return hash_to_content

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines:
                normalized = self._hasher.normalize(line)
                if not normalized:
                    continue

                line_hash = self._hasher.hash(normalized, pre_normalized=True)
                if line_hash in ai_hashes:
                    hash_to_content[line_hash] = line.rstrip('\n\r')

        except Exception as e:
            self._logger.error(f"Failed to read {file_path}: {e}")

        return hash_to_content
