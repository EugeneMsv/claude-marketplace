"""Tracking data persistence infrastructure."""

import json
from pathlib import Path
from typing import Optional
from domain.tracking_data import TrackingData
from domain.contribution_stats import LineStats, ContributorStats


class TrackingRepository:
    """Repository for persisting TrackingData to JSON files."""

    def __init__(self, git_root: Path, branch_name: str):
        """Initialize tracking repository.

        Args:
            git_root: Git repository root directory
            branch_name: Sanitized branch name for file naming
        """
        self._git_root = git_root
        self._tracking_path = git_root / '.claude' / 'herald' / f'{branch_name}.json'

    def exists(self) -> bool:
        """Check if tracking file exists.

        Returns:
            True if tracking file exists
        """
        return self._tracking_path.exists()

    def load(self) -> Optional[TrackingData]:
        """Load tracking data from file.

        Returns:
            TrackingData object, or None if file doesn't exist
        """
        if not self._tracking_path.exists():
            return None

        try:
            with open(self._tracking_path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        # Reconstruct TrackingData from dict
        tracking = TrackingData(data.get('branch', ''))
        tracking.merge_base = data.get('merge_base')

        stats = data.get('stats')
        if stats:
            tracking.stats = stats

        tracking.last_updated = data.get('last_updated')
        tracking.pending_inject_head = data.get('pending_inject_head')
        tracking.files_tracked = data.get('files_tracked', [])
        tracking.ai_deleted_files = set(data.get('ai_deleted_files', []))

        if 'ai_line_hashes' in data:
            tracking.ai_line_hashes = data['ai_line_hashes']

        if 'ai_removed_line_hashes' in data:
            tracking.ai_removed_line_hashes = data['ai_removed_line_hashes']

        return tracking

    def save(self, tracking: TrackingData) -> bool:
        """Save tracking data to file.

        Args:
            tracking: TrackingData to persist

        Returns:
            True if successful, False otherwise
        """
        # Convert to dict for JSON serialization
        # ai_line_hashes and ai_removed_line_hashes are already Dict[str, int],
        # which is JSON-compatible, so no conversion needed
        data = {
            'branch': tracking.branch,
            'merge_base': tracking.merge_base,
            'files_tracked': tracking.files_tracked,
            'stats': tracking.stats,
            'last_updated': tracking.last_updated,
            'pending_inject_head': tracking.pending_inject_head,
            'ai_line_hashes': tracking.ai_line_hashes,
            'ai_removed_line_hashes': tracking.ai_removed_line_hashes,
            'ai_deleted_files': list(tracking.ai_deleted_files),
        }

        # Atomic write with temp file
        try:
            self._tracking_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._tracking_path.with_suffix('.tmp')

            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self._tracking_path)
            return True
        except Exception:
            return False

    @property
    def tracking_path(self) -> Path:
        """Get path to tracking file."""
        return self._tracking_path
