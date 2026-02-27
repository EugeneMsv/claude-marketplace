"""Statistics calculation service."""

from pathlib import Path
from typing import Dict, Set
from domain.tracking_data import TrackingData
from domain.diff import Diff
from domain.contribution_stats import ContributionStats, FileTypeStats, LineStats, ContributorStats
from domain.line_hasher import LineHasher


class StatsCalculator:
    """Service for calculating AI vs human contribution statistics.

    Pure calculation logic with no I/O dependencies.
    """

    def __init__(self, hasher: LineHasher, tracked_extensions: Set[str]):
        """Initialize stats calculator.

        Args:
            hasher: LineHasher instance for consistent hashing
            tracked_extensions: Set of file extensions to include in stats (e.g. {'.py', '.java'})
        """
        self._hasher = hasher
        self._tracked_extensions = tracked_extensions

    def calculate(self, tracking: TrackingData, diff: Diff) -> ContributionStats:
        """Calculate contribution statistics.

        Args:
            tracking: TrackingData with AI line hashes
            diff: Diff object with file changes

        Returns:
            ContributionStats object with aggregated statistics
        """
        total_ai_added = 0
        total_ai_removed = 0
        total_added = 0
        total_removed = 0
        by_file_type: Dict[str, Dict] = {}

        # Process each AI-tracked file (files where Write/Edit tool calls fired)
        for file_path in tracking.files_tracked:
            # Get diff for this file
            file_diff = diff.get_file_diff(file_path)
            if not file_diff:
                # File not in diff (unchanged)
                continue

            # Count AI vs human lines for additions
            ai_added_count, total_added_count = self._count_file_lines(
                file_path,
                file_diff.added_lines,
                tracking
            )

            # Count AI vs human lines for removals
            ai_removed_count, total_removed_count = self._count_removed_lines(
                file_path,
                file_diff.removed_lines,
                tracking
            )

            total_ai_added += ai_added_count
            total_ai_removed += ai_removed_count
            total_added += total_added_count
            total_removed += total_removed_count

            # Aggregate by file extension
            ext = Path(file_path).suffix.lower()
            if ext not in by_file_type:
                by_file_type[ext] = {
                    'ai_added': 0,
                    'ai_removed': 0,
                    'total_added': 0,
                    'total_removed': 0,
                }

            by_file_type[ext]['ai_added'] += ai_added_count
            by_file_type[ext]['ai_removed'] += ai_removed_count
            by_file_type[ext]['total_added'] += total_added_count
            by_file_type[ext]['total_removed'] += total_removed_count

        # Process human-only files: changed in the diff but never touched by AI tools.
        # file_diff.added_lines / removed_lines are the `+`/`-` hunk lines from
        # `git diff --unified=0 <merge-base> HEAD` — only changed lines, not the full file.
        # tracking has no AI hashes for these files, so _count_file_lines returns (0, total),
        # attributing every non-blank changed line to human.
        tracked_files_set = set(tracking.files_tracked)
        for file_path in diff.get_changed_files():
            if file_path in tracked_files_set:
                continue
            if Path(file_path).suffix.lower() not in self._tracked_extensions:
                continue
            file_diff = diff.get_file_diff(file_path)
            _, added_count = self._count_file_lines(file_path, file_diff.added_lines, tracking)
            _, removed_count = self._count_removed_lines(file_path, file_diff.removed_lines, tracking)
            total_added += added_count
            total_removed += removed_count
            ext = Path(file_path).suffix.lower()
            if ext not in by_file_type:
                by_file_type[ext] = {
                    'ai_added': 0,
                    'ai_removed': 0,
                    'total_added': 0,
                    'total_removed': 0,
                }
            by_file_type[ext]['total_added'] += added_count
            by_file_type[ext]['total_removed'] += removed_count

        # Build overall ContributorStats
        ai_total = total_ai_added + total_ai_removed
        human_added = total_added - total_ai_added
        human_removed = total_removed - total_ai_removed
        human_total = human_added + human_removed
        overall_total = ai_total + human_total

        ai_stats = ContributorStats(
            total=LineStats(
                lines=ai_total,
                percentage=round(ai_total / overall_total * 100, 1) if overall_total > 0 else 0.0
            ),
            added=LineStats(
                lines=total_ai_added,
                percentage=round(total_ai_added / total_added * 100, 1) if total_added > 0 else 0.0
            ),
            removed=LineStats(
                lines=total_ai_removed,
                percentage=round(total_ai_removed / total_removed * 100, 1) if total_removed > 0 else 0.0
            )
        )

        human_stats = ContributorStats(
            total=LineStats(
                lines=human_total,
                percentage=round(human_total / overall_total * 100, 1) if overall_total > 0 else 0.0
            ),
            added=LineStats(
                lines=human_added,
                percentage=round(human_added / total_added * 100, 1) if total_added > 0 else 0.0
            ),
            removed=LineStats(
                lines=human_removed,
                percentage=round(human_removed / total_removed * 100, 1) if total_removed > 0 else 0.0
            )
        )

        # Calculate file type stats (for backward compatibility, keep FileTypeStats)
        file_type_stats = {}
        for ext, stats_dict in by_file_type.items():
            # Count all changed files with this extension (AI-tracked + human-only)
            file_count = len([
                f for f in diff.get_changed_files()
                if Path(f).suffix.lower() == ext
            ])

            # For backward compatibility, FileTypeStats only has total lines
            ext_ai_total = stats_dict['ai_added'] + stats_dict['ai_removed']
            ext_total_lines = stats_dict['total_added'] + stats_dict['total_removed']
            ext_human_total = ext_total_lines - ext_ai_total

            # Calculate percentage
            if ext_total_lines > 0:
                ai_pct = round(ext_ai_total / ext_total_lines * 100, 1)
            else:
                ai_pct = 0.0

            file_type_stats[ext] = FileTypeStats(
                ai_lines=ext_ai_total,
                human_lines=ext_human_total,
                total_lines=ext_total_lines,
                ai_percentage=ai_pct,
                file_count=file_count
            )

        return ContributionStats(
            ai_stats=ai_stats,
            human_stats=human_stats,
            by_file_type=file_type_stats
        )

    def _count_file_lines(
        self,
        file_path: str,
        added_lines: list,
        tracking: TrackingData
    ) -> tuple:
        """Count AI vs human lines in added lines.

        Uses occurrence counts from tracking data. If a line appears multiple
        times in added_lines, each occurrence is checked against the tracked
        count. Once the tracked count is exhausted, additional occurrences
        are attributed to human.

        Args:
            file_path: Relative file path
            added_lines: Lines added in this file
            tracking: TrackingData with AI hashes and counts

        Returns:
            Tuple of (ai_count, total_count)
        """
        # Get mutable copy of hash counts for consumption
        ai_hashes = tracking.get_ai_hashes_for_file(file_path).copy()
        ai_count = 0
        total_count = 0

        for line in added_lines:
            normalized = self._hasher.normalize(line)
            if normalized:  # Skip empty lines
                total_count += 1
                line_hash = self._hasher.hash(normalized, pre_normalized=True)

                # Check if hash exists with remaining count > 0
                if line_hash in ai_hashes and ai_hashes[line_hash] > 0:
                    ai_count += 1
                    ai_hashes[line_hash] -= 1  # Consume one occurrence

        return ai_count, total_count

    def _count_removed_lines(
        self,
        file_path: str,
        removed_lines: list,
        tracking: TrackingData
    ) -> tuple:
        """Count AI vs human lines in removed lines.

        Checks who REMOVED the lines (removal attribution),
        not who originally authored them.

        Uses occurrence counts from tracking data. If a line appears multiple
        times in removed_lines, each occurrence is checked against the tracked
        count. Once the tracked count is exhausted, additional occurrences
        are attributed to human.

        Args:
            file_path: Relative file path
            removed_lines: Lines removed in this file
            tracking: TrackingData with AI removal hashes and counts

        Returns:
            Tuple of (ai_count, total_count)
        """
        # Get mutable copy of hash counts for consumption
        ai_removed_hashes = tracking.get_ai_removed_hashes_for_file(file_path).copy()
        ai_count = 0
        total_count = 0

        for line in removed_lines:
            normalized = self._hasher.normalize(line)
            if normalized:  # Skip empty lines
                total_count += 1
                line_hash = self._hasher.hash(normalized, pre_normalized=True)

                # Check if hash exists with remaining count > 0
                if line_hash in ai_removed_hashes and ai_removed_hashes[line_hash] > 0:
                    ai_count += 1
                    ai_removed_hashes[line_hash] -= 1  # Consume one occurrence

        return ai_count, total_count
