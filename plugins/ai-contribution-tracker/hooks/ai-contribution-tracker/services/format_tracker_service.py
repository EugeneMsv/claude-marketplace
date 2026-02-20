"""Format tracker service for preserving attribution after formatting."""

import os
import time
from collections import Counter
from logging import Logger
from pathlib import Path
from typing import Dict, List, Optional, Set
from domain.format_snapshot import FormatSnapshot
from domain.line_hasher import LineHasher
from domain.token_normalizer import TokenNormalizer
from infrastructure.git_repository import GitRepository
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository


class FormatTrackerService:
    """
    Service for preserving AI attribution after formatting completes.

    This service runs in the PostToolUse hook after formatters execute.
    It loads the pre-format snapshot, compares with current state using
    token matching, and updates tracking data with new hashes.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        config: Configuration,
        hasher: LineHasher,
        token_normalizer: TokenNormalizer,
        logger: Logger
    ):
        """Initialize format tracker service.

        Args:
            git_repo: GitRepository for git operations
            config: Configuration settings
            hasher: LineHasher for computing line hashes
            token_normalizer: TokenNormalizer for token comparison
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._config = config
        self._hasher = hasher
        self._token_normalizer = token_normalizer
        self._logger = logger

    def process_post_format(self, pid: int) -> bool:
        """
        Process formatting completion and update attribution.

        Args:
            pid: Process ID of the command

        Returns:
            True if processing succeeded
        """
        # Get git root
        git_root = self._git_repo.get_root()
        if not git_root:
            return False

        # Find snapshot file for this PID
        snapshot_path = git_root / '.claude' / f'format-snapshot-{pid}.json'

        if not snapshot_path.exists():
            self._logger.info(f"No snapshot found for PID {pid}")
            # Clean up stale snapshots and exit
            self._cleanup_stale_snapshots(git_root)
            return False

        try:
            # Load snapshot
            snapshot = FormatSnapshot.load_from_file(str(snapshot_path))

            self._logger.info(f"Loaded snapshot for branch {snapshot.branch}")

            # Get current branch
            branch = self._git_repo.get_current_branch()
            if not branch or branch != snapshot.branch:
                self._logger.warning(f"Branch mismatch: {branch} != {snapshot.branch}")
                return False

            # Load tracking data
            sanitized_branch = GitRepository.sanitize_branch_name(branch)
            tracking_repo = TrackingRepository(git_root, sanitized_branch)
            tracking = tracking_repo.load()

            if not tracking:
                self._logger.warning("No tracking data found")
                return False

            # Process each file in snapshot
            updated = False
            for file_path, hash_to_content in snapshot.files.items():
                if self._process_file(git_root, file_path, hash_to_content, tracking):
                    updated = True

            # Save updated tracking data
            if updated:
                tracking_repo.save(tracking)
                self._logger.info("Updated tracking data with formatted line hashes")

            return True

        except Exception as e:
            self._logger.error(f"Failed to process format snapshot: {e}")
            return False
        finally:
            # Always delete snapshot file
            try:
                snapshot_path.unlink()
                self._logger.info(f"Deleted snapshot file: {snapshot_path}")
            except Exception as e:
                self._logger.error(f"Failed to delete snapshot: {e}")

            # Clean up stale snapshots
            self._cleanup_stale_snapshots(git_root)

    def _process_file(
        self,
        git_root: Path,
        file_path: str,
        hash_to_content: Dict[str, str],
        tracking
    ) -> bool:
        """
        Process a single file: compare snapshot with current state.

        Args:
            git_root: Git repository root
            file_path: Relative path to file
            hash_to_content: Mapping of old hash → old content
            tracking: TrackingData to update

        Returns:
            True if tracking data was updated
        """
        if not hash_to_content:
            return False

        # Read current file content
        full_path = git_root / file_path
        if not full_path.exists():
            self._logger.warning(f"File no longer exists: {file_path}")
            return False

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                current_lines = f.readlines()
        except Exception as e:
            self._logger.error(f"Failed to read {file_path}: {e}")
            return False

        # Build AI-attributed sections from snapshot
        ai_content_sections = list(hash_to_content.values())
        if not ai_content_sections:
            return False

        # Join all AI content into one text block for token comparison
        ai_text = '\n'.join(ai_content_sections)

        # Join all current lines into one text block
        current_text = ''.join(line.rstrip('\n\r') for line in current_lines)

        # Extract tokens from both
        ai_tokens = self._token_normalizer.extract_tokens(ai_text)
        current_tokens = self._token_normalizer.extract_tokens(current_text)

        # Calculate token overlap
        overlap = self._token_normalizer.calculate_token_overlap(ai_tokens, current_tokens)

        self._logger.info(f"File {file_path}: token overlap = {overlap:.2%}")

        # If overlap >= 80%, this is likely just formatting
        if overlap >= 0.8:
            # Hash all current lines and count occurrences
            hash_counts = Counter()
            for line in current_lines:
                normalized = self._hasher.normalize(line)
                if not normalized:
                    continue
                line_hash = self._hasher.hash(normalized, pre_normalized=True)
                hash_counts[line_hash] += 1

            # Add new hashes with counts to tracking (preserves old hashes too)
            for line_hash, count in hash_counts.items():
                tracking.add_ai_line_hash(file_path, line_hash, count=count)

            total_lines = sum(hash_counts.values())
            self._logger.info(f"Added {len(hash_counts)} unique hashes ({total_lines} total lines) for {file_path}")

            return True
        else:
            self._logger.info(f"Token overlap too low ({overlap:.2%}), likely semantic change")
            return False

    def _cleanup_stale_snapshots(self, git_root: Path) -> None:
        """
        Remove stale snapshot files older than 1 hour.

        Args:
            git_root: Git repository root
        """
        snapshot_dir = git_root / '.claude'
        if not snapshot_dir.exists():
            return

        try:
            current_time = time.time()
            stale_threshold = 3600  # 1 hour in seconds

            for snapshot_file in snapshot_dir.glob('format-snapshot-*.json'):
                try:
                    file_age = current_time - snapshot_file.stat().st_mtime
                    if file_age > stale_threshold:
                        snapshot_file.unlink()
                        self._logger.info(f"Cleaned up stale snapshot: {snapshot_file.name}")
                except Exception as e:
                    self._logger.error(f"Failed to clean up {snapshot_file.name}: {e}")

        except Exception as e:
            self._logger.error(f"Failed to clean up snapshots: {e}")
