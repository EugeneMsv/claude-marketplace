"""Contribution statistics domain models."""

from typing import Dict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LineStats:
    """Statistics for a specific line category (total, added, or removed).

    Immutable value object representing line count and percentage
    for a single category.
    """
    lines: int
    percentage: float


@dataclass(frozen=True)
class ContributorStats:
    """Statistics for a single contributor type (AI or human).

    Immutable value object containing total, added, and removed
    line statistics for one contributor.
    """
    total: LineStats
    added: LineStats
    removed: LineStats


@dataclass(frozen=True)
class IgnoredFilesStats:
    """Statistics for ignored files (excluded from AI/Human percentages).

    Immutable value object containing line counts and the set of patterns that
    matched at least one file in the commit.
    """
    total: int
    added: int
    removed: int
    matched_patterns: frozenset


@dataclass(frozen=True)
class FileTypeStats:
    """Statistics for a specific file type/extension.

    Immutable value object representing contribution stats aggregated
    by file extension.
    """
    ai_lines: int
    human_lines: int
    total_lines: int
    ai_percentage: float
    file_count: int


class ContributionStats:
    """Value object representing AI vs human contribution statistics.

    Immutable once created. Contains aggregate statistics across all tracked
    files and per-file-type breakdowns.
    """

    def __init__(
        self,
        ai_stats: ContributorStats,
        human_stats: ContributorStats,
        by_file_type: Dict[str, FileTypeStats],
        ignored_files: IgnoredFilesStats = None
    ):
        """Initialize contribution statistics.

        Args:
            ai_stats: ContributorStats for AI contributions
            human_stats: ContributorStats for human contributions
            by_file_type: Statistics broken down by file extension
            ignored_files: Stats for ignored files (excluded from AI/Human %)
        """
        self._ai_stats = ai_stats
        self._human_stats = human_stats
        self._by_file_type = by_file_type.copy()
        self._ignored_files: IgnoredFilesStats = ignored_files if ignored_files is not None else IgnoredFilesStats(
            total=0, added=0, removed=0, matched_patterns=frozenset()
        )

    @classmethod
    def from_dict(cls, data: Dict) -> 'ContributionStats':
        """Reconstruct ContributionStats from a dictionary (e.g. saved tracking data).

        Args:
            data: Dictionary as produced by to_dict()

        Returns:
            ContributionStats instance
        """
        def _load_contributor(section: Dict) -> ContributorStats:
            return ContributorStats(
                total=LineStats(lines=section['total']['lines'],
                                percentage=section['total']['percentage']),
                added=LineStats(lines=section['added']['lines'],
                                percentage=section['added']['percentage']),
                removed=LineStats(lines=section['removed']['lines'],
                                  percentage=section['removed']['percentage']),
            )

        ai_stats = _load_contributor(data.get('ai', {}))
        human_stats = _load_contributor(data.get('human', {}))

        by_file_type = {}
        for ext, ft in data.get('by_file_type', {}).items():
            by_file_type[ext] = FileTypeStats(
                ai_lines=ft['ai_lines'],
                human_lines=ft['human_lines'],
                total_lines=ft['total_lines'],
                ai_percentage=ft['ai_percentage'],
                file_count=ft['file_count'],
            )

        ig_data = data.get('ignored_files', {})
        ignored_files = IgnoredFilesStats(
            total=ig_data.get('total', 0),
            added=ig_data.get('added', 0),
            removed=ig_data.get('removed', 0),
            matched_patterns=frozenset(ig_data.get('matched_patterns', [])),
        )

        return cls(
            ai_stats=ai_stats,
            human_stats=human_stats,
            by_file_type=by_file_type,
            ignored_files=ignored_files,
        )

    @property
    def ai_stats(self) -> ContributorStats:
        """Get AI contributor statistics."""
        return self._ai_stats

    @property
    def human_stats(self) -> ContributorStats:
        """Get human contributor statistics."""
        return self._human_stats

    @property
    def ai_lines(self) -> int:
        """Get AI-authored line count."""
        return self._ai_stats.total.lines

    @property
    def human_lines(self) -> int:
        """Get human-authored line count."""
        return self._human_stats.total.lines

    @property
    def total_lines(self) -> int:
        """Get total line count."""
        return self._ai_stats.total.lines + self._human_stats.total.lines

    @property
    def ai_percentage(self) -> float:
        """Get AI contribution percentage."""
        return self._ai_stats.total.percentage

    @property
    def ignored_files(self) -> IgnoredFilesStats:
        """Get ignored file statistics."""
        return self._ignored_files

    @property
    def by_file_type(self) -> Dict[str, FileTypeStats]:
        """Get per-file-type statistics."""
        return self._by_file_type.copy()

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON
        """
        total_changed = self._ai_stats.total.lines + self._human_stats.total.lines
        total_added = self._ai_stats.added.lines + self._human_stats.added.lines
        total_removed = self._ai_stats.removed.lines + self._human_stats.removed.lines

        return {
            'total_changed_lines': total_changed,
            'total_added_lines': total_added,
            'total_removed_lines': total_removed,
            'ai': {
                'total': {
                    'lines': self._ai_stats.total.lines,
                    'percentage': self._ai_stats.total.percentage
                },
                'added': {
                    'lines': self._ai_stats.added.lines,
                    'percentage': self._ai_stats.added.percentage
                },
                'removed': {
                    'lines': self._ai_stats.removed.lines,
                    'percentage': self._ai_stats.removed.percentage
                }
            },
            'human': {
                'total': {
                    'lines': self._human_stats.total.lines,
                    'percentage': self._human_stats.total.percentage
                },
                'added': {
                    'lines': self._human_stats.added.lines,
                    'percentage': self._human_stats.added.percentage
                },
                'removed': {
                    'lines': self._human_stats.removed.lines,
                    'percentage': self._human_stats.removed.percentage
                }
            },
            'by_file_type': {
                ext: {
                    'ai_lines': stats.ai_lines,
                    'human_lines': stats.human_lines,
                    'total_lines': stats.total_lines,
                    'ai_percentage': stats.ai_percentage,
                    'file_count': stats.file_count
                }
                for ext, stats in self._by_file_type.items()
            },
            'ignored_files': {
                'total': self._ignored_files.total,
                'added': self._ignored_files.added,
                'removed': self._ignored_files.removed,
                'matched_patterns': sorted(self._ignored_files.matched_patterns),
            }
        }

    def format_compact(self) -> str:
        """Format statistics as compact tag for MR titles.

        Returns:
            Compact format string, e.g. '[AI: 85%]'
        """
        return f"[AI: {int(round(self._ai_stats.total.percentage))}%]"

    def _format_tracked_extensions(self) -> str:
        """Format tracked file extensions list.

        Returns:
            Formatted string showing tracked extensions,
            or empty string if no extensions tracked
        """
        if not self._by_file_type:
            return ""

        # Filter extensions with changes
        extensions_with_changes = [
            ext for ext, stats in self._by_file_type.items()
            if stats.total_lines > 0
        ]

        if not extensions_with_changes:
            return ""

        # Sort alphabetically for consistency
        extensions_with_changes.sort()

        return f"Tracked: {', '.join(extensions_with_changes)}"

    def format_message(self) -> str:
        """Format statistics as human-readable message for commit.

        Returns:
            Formatted message string with tracked extensions
        """
        # Always use new format with added/removed breakdown
        total_added = self._ai_stats.added.lines + self._human_stats.added.lines
        total_removed = self._ai_stats.removed.lines + self._human_stats.removed.lines
        msg = f"Overall: +{total_added} -{total_removed}\n"
        msg += f"  AI: {self._ai_stats.total.lines} lines ({self._ai_stats.total.percentage}%)\n"
        msg += f"    +{self._ai_stats.added.lines} ({self._ai_stats.added.percentage}%)\n"
        msg += f"    -{self._ai_stats.removed.lines} ({self._ai_stats.removed.percentage}%)\n"
        msg += f"  Human: {self._human_stats.total.lines} lines ({self._human_stats.total.percentage}%)\n"
        msg += f"    +{self._human_stats.added.lines} ({self._human_stats.added.percentage}%)\n"
        msg += f"    -{self._human_stats.removed.lines} ({self._human_stats.removed.percentage}%)"

        # Add tracked extensions list if available
        tracked = self._format_tracked_extensions()
        if tracked:
            msg += f"\n{tracked}"

        # Append ignored-files section when there are ignored lines
        if self._ignored_files.total > 0:
            msg += f"\n  Ignored: {self._ignored_files.total} lines excluded"
            msg += f"\n    +{self._ignored_files.added} -{self._ignored_files.removed}"
            if self._ignored_files.matched_patterns:
                patterns_str = ", ".join(sorted(self._ignored_files.matched_patterns))
                msg += f"\n    Matched patterns: {patterns_str}"

        return msg

    def format_description(self) -> str:
        """Format statistics as markdown section for MR descriptions.

        Returns:
            Formatted markdown string with heading and code fence
        """
        return f"## AI Contribution Stats\n\n```\n{self.format_message()}\n```"
