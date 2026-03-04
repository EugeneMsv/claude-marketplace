"""Tracking data persistence infrastructure."""

import json
from pathlib import Path
from typing import Optional
from domain.tracking_data import TrackingData
from domain.contribution_stats import LineStats, ContributorStats


class TrackingRepository:
    """Repository for persisting TrackingData to JSON files.

    Handles serialization/deserialization of TrackingData, including
    conversion between old format (lists) and new format (dicts with counts).
    """

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

        # Migrate old format stats to new format if needed
        stats = data.get('stats')
        if stats:
            tracking.stats = self._migrate_stats_format(stats)

        tracking.last_updated = data.get('last_updated')
        tracking.pending_inject_head = data.get('pending_inject_head')
        tracking.files_tracked = data.get('files_tracked', [])
        tracking.ai_deleted_files = set(data.get('ai_deleted_files', []))

        # Migrate hash data from old format (list) to new format (dict with counts)
        if 'ai_line_hashes' in data:
            for file_path, hash_data in data['ai_line_hashes'].items():
                tracking.ai_line_hashes[file_path] = self._migrate_hash_format(hash_data)

        if 'ai_removed_line_hashes' in data:
            for file_path, hash_data in data['ai_removed_line_hashes'].items():
                tracking.ai_removed_line_hashes[file_path] = self._migrate_hash_format(hash_data)

        return tracking

    def _migrate_hash_format(self, hash_data) -> dict:
        """Migrate hash data from old format to new format.

        Old format: list of hashes (e.g., ["hash1", "hash2", "hash1"])
        New format: dict mapping hash to count (e.g., {"hash1": 2, "hash2": 1})

        Args:
            hash_data: Hash data in old or new format

        Returns:
            Dict mapping hash to occurrence count
        """
        # Check if already new format (dict)
        if isinstance(hash_data, dict):
            return hash_data

        # Old format (list) - convert to dict with count=1 for each unique hash
        # Note: Old format used set internally, so duplicates were lost.
        # We initialize each hash with count=1 for backward compatibility.
        if isinstance(hash_data, list):
            return {hash_value: 1 for hash_value in hash_data}

        # Fallback for unexpected format
        return {}

    def _migrate_stats_format(self, stats: dict) -> dict:
        """Migrate old stats format to new format.

        Args:
            stats: Stats dictionary (old or new format)

        Returns:
            Stats dictionary in new format
        """
        # Check if already new format
        if 'ai' in stats and 'human' in stats:
            return stats

        # Old format - migrate to new
        ai_lines = stats.get('ai_lines', 0)
        human_lines = stats.get('human_lines', 0)
        total_lines = stats.get('total_lines', 0)
        ai_percentage = stats.get('ai_percentage', 0.0)

        human_percentage = round((human_lines / total_lines * 100), 1) if total_lines > 0 else 0.0

        return {
            'total_changed_lines': total_lines,
            'total_added_lines': total_lines,
            'total_removed_lines': 0,
            'ai': {
                'total': {'lines': ai_lines, 'percentage': ai_percentage},
                'added': {'lines': ai_lines, 'percentage': ai_percentage},
                'removed': {'lines': 0, 'percentage': 0.0}
            },
            'human': {
                'total': {'lines': human_lines, 'percentage': human_percentage},
                'added': {'lines': human_lines, 'percentage': human_percentage},
                'removed': {'lines': 0, 'percentage': 0.0}
            },
            'by_file_type': stats.get('by_file_type', {})
        }

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
