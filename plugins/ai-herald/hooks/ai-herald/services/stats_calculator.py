"""Statistics calculation service."""

from pathlib import Path
from typing import Dict, Set
from domain.tracking_data import TrackingData
from domain.diff import Diff
from domain.contribution_stats import IgnoredFilesStats, ContributionStats, FileTypeStats, LineStats, ContributorStats
from domain.ignored_files_detector import IgnoredFilesDetector
from domain.line_hasher import LineHasher


class _IgnoredFilesAccumulator:
    """Mutable accumulator for ignored file stats."""

    def __init__(self, hasher: LineHasher, detector: IgnoredFilesDetector):
        self._hasher = hasher
        self._detector = detector
        self._added = 0
        self._removed = 0
        self._matched_patterns: Set[str] = set()

    def accumulate(self, file_path: str, file_diff) -> None:
        self._matched_patterns.update(self._detector.matched_patterns(file_path))
        self._added += len([l for l in file_diff.added_lines if self._hasher.normalize(l)])
        self._removed += len([l for l in file_diff.removed_lines if self._hasher.normalize(l)])

    def build_ignored_files_stats(self) -> IgnoredFilesStats:
        return IgnoredFilesStats(
            total=self._added + self._removed,
            added=self._added,
            removed=self._removed,
            matched_patterns=frozenset(self._matched_patterns),
        )


class _ContributorAccumulator:
    """Mutable accumulator for AI and human contributor stats."""

    def __init__(self):
        self._ai_added = 0
        self._ai_removed = 0
        self._human_added = 0
        self._human_removed = 0
        self._total_added = 0    # ai_added + human_added across all files
        self._total_removed = 0  # ai_removed + human_removed across all files
        self._by_ext: Dict[str, Dict] = {}

    def add_file(self, ai_added: int, ai_removed: int, human_added: int, human_removed: int, file_ext: str) -> None:
        self._ai_added += ai_added
        self._ai_removed += ai_removed
        self._human_added += human_added
        self._human_removed += human_removed
        self._total_added += ai_added + human_added
        self._total_removed += ai_removed + human_removed
        if file_ext not in self._by_ext:
            self._by_ext[file_ext] = {'ai_added': 0, 'ai_removed': 0, 'human_added': 0, 'human_removed': 0}
        self._by_ext[file_ext]['ai_added'] += ai_added
        self._by_ext[file_ext]['ai_removed'] += ai_removed
        self._by_ext[file_ext]['human_added'] += human_added
        self._by_ext[file_ext]['human_removed'] += human_removed

    def build_ai_stats(self) -> ContributorStats:
        ai_total = self._ai_added + self._ai_removed
        overall_total = ai_total + self._human_added + self._human_removed
        return ContributorStats(
            total=LineStats(
                lines=ai_total,
                percentage=round(ai_total / overall_total * 100, 1) if overall_total > 0 else 0.0,
            ),
            added=LineStats(
                lines=self._ai_added,
                percentage=round(self._ai_added / self._total_added * 100, 1) if self._total_added > 0 else 0.0,
            ),
            removed=LineStats(
                lines=self._ai_removed,
                percentage=round(self._ai_removed / self._total_removed * 100, 1) if self._total_removed > 0 else 0.0,
            ),
        )

    def build_human_stats(self) -> ContributorStats:
        human_total = self._human_added + self._human_removed
        overall_total = self._ai_added + self._ai_removed + human_total
        return ContributorStats(
            total=LineStats(
                lines=human_total,
                percentage=round(human_total / overall_total * 100, 1) if overall_total > 0 else 0.0,
            ),
            added=LineStats(
                lines=self._human_added,
                percentage=round(self._human_added / self._total_added * 100, 1) if self._total_added > 0 else 0.0,
            ),
            removed=LineStats(
                lines=self._human_removed,
                percentage=round(self._human_removed / self._total_removed * 100, 1) if self._total_removed > 0 else 0.0,
            ),
        )

    def build_file_type_stats(self, diff: Diff) -> Dict[str, FileTypeStats]:
        result = {}
        for ext, counts in self._by_ext.items():
            file_count = len([f for f in diff.get_changed_files() if Path(f).suffix.lower() == ext])
            ext_ai_total = counts['ai_added'] + counts['ai_removed']
            ext_human_total = counts['human_added'] + counts['human_removed']
            ext_total = ext_ai_total + ext_human_total
            ai_pct = round(ext_ai_total / ext_total * 100, 1) if ext_total > 0 else 0.0
            result[ext] = FileTypeStats(
                ai_lines=ext_ai_total,
                human_lines=ext_human_total,
                total_lines=ext_total,
                ai_percentage=ai_pct,
                file_count=file_count,
            )
        return result


class StatsCalculator:
    """Service for calculating AI vs human contribution statistics.

    Pure calculation logic with no I/O dependencies.
    """

    def __init__(self, hasher: LineHasher, tracked_extensions: Set[str], ignored_files_detector: IgnoredFilesDetector):
        """Initialize stats calculator.

        Args:
            hasher: LineHasher instance for consistent hashing
            tracked_extensions: Set of file extensions to include in stats (e.g. {'.py', '.java'})
            ignored_files_detector: Detector for ignored files (excluded from AI/Human %)
        """
        self._hasher = hasher
        self._tracked_extensions = tracked_extensions
        self._ignored_files_detector = ignored_files_detector

    def calculate(self, tracking: TrackingData, diff: Diff) -> ContributionStats:
        """Calculate contribution statistics.

        Args:
            tracking: TrackingData with AI line hashes
            diff: Diff object with file changes

        Returns:
            ContributionStats object with aggregated statistics
        """
        ignored_acc = _IgnoredFilesAccumulator(self._hasher, self._ignored_files_detector)
        contributor_acc = _ContributorAccumulator()
        ai_tracked = set(tracking.files_tracked)
        all_files = ai_tracked | set(diff.get_changed_files())

        for file_path in all_files:
            file_diff = diff.get_file_diff(file_path)
            if not file_diff:
                continue
            # Extension filter only needed for files AI never touched
            if file_path not in ai_tracked and self._file_ext(file_path) not in self._tracked_extensions:
                continue
            if self._ignored_files_detector.is_ignored(file_path):
                ignored_acc.accumulate(file_path, file_diff)
                continue
            ai_added, total_added = self._count_file_lines(file_path, file_diff.added_lines, tracking)
            ai_removed, total_removed = self._count_file_removals(file_path, file_diff.removed_lines, tracking)
            contributor_acc.add_file(
                ai_added=ai_added, ai_removed=ai_removed,
                human_added=total_added - ai_added, human_removed=total_removed - ai_removed,
                file_ext=self._file_ext(file_path),
            )

        return ContributionStats(
            ai_stats=contributor_acc.build_ai_stats(),
            human_stats=contributor_acc.build_human_stats(),
            by_file_type=contributor_acc.build_file_type_stats(diff),
            ignored_files=ignored_acc.build_ignored_files_stats(),
        )

    @staticmethod
    def _file_ext(file_path: str) -> str:
        """Return the lowercased file extension."""
        return Path(file_path).suffix.lower()

    def _count_file_removals(self, file_path: str, removed_lines: list, tracking: TrackingData) -> tuple:
        """Count AI vs human removed lines, honouring the ai_deleted_files shortcut.

        If the file is in ai_deleted_files, all removed lines are attributed to AI
        without per-line hash matching.

        Args:
            file_path: Relative file path
            removed_lines: Lines removed in this file
            tracking: TrackingData with AI removal hashes

        Returns:
            Tuple of (ai_count, total_count)
        """
        if file_path in tracking.ai_deleted_files:
            total = len([l for l in removed_lines if self._hasher.normalize(l)])
            return total, total
        return self._count_removed_lines(file_path, removed_lines, tracking)

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
