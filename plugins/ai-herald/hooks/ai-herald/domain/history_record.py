"""History record domain models for per-commit AI contribution tracking."""

import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class HistoryExtensionStats:
    """AI/human breakdown for a single file extension within a commit.

    Immutable value object stored per extension in HistoryRecord.
    Deliberately omits file_count and total_lines (available in FileTypeStats)
    since history queries only need the AI/human split.
    """

    ai_percentage: float
    ai_lines: int
    human_lines: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Dictionary with ai_percentage, ai_lines, human_lines keys.
        """
        return {
            'ai_percentage': self.ai_percentage,
            'ai_lines': self.ai_lines,
            'human_lines': self.human_lines,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryExtensionStats':
        """Deserialize from a dictionary.

        Args:
            data: Dictionary as produced by to_dict().

        Returns:
            HistoryExtensionStats instance.

        Raises:
            KeyError: If a required field is missing.
        """
        return cls(
            ai_percentage=float(data['ai_percentage']),
            ai_lines=int(data['ai_lines']),
            human_lines=int(data['human_lines']),
        )


@dataclass(frozen=True)
class HistoryIgnoredStats:
    """Stats for lines excluded from attribution via ignored_paths globs.

    Immutable value object. Uses explicit long field names (total_lines,
    lines_added, lines_removed) to distinguish from IgnoredFilesStats
    (which uses total, added, removed). matched_patterns is a tuple
    rather than frozenset for deterministic JSON serialization.
    """

    total_lines: int
    lines_added: int
    lines_removed: int
    matched_patterns: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Dictionary with all fields; matched_patterns as list.
        """
        return {
            'total_lines': self.total_lines,
            'lines_added': self.lines_added,
            'lines_removed': self.lines_removed,
            'matched_patterns': list(self.matched_patterns),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryIgnoredStats':
        """Deserialize from a dictionary.

        Args:
            data: Dictionary as produced by to_dict(). matched_patterns
                defaults to empty list if missing.

        Returns:
            HistoryIgnoredStats instance.

        Raises:
            KeyError: If a required numeric field is missing.
        """
        return cls(
            total_lines=int(data['total_lines']),
            lines_added=int(data['lines_added']),
            lines_removed=int(data['lines_removed']),
            matched_patterns=tuple(data.get('matched_patterns', [])),
        )

    @classmethod
    def empty(cls) -> 'HistoryIgnoredStats':
        """Return a zero-valued instance for commits with no ignored lines."""
        return cls(total_lines=0, lines_added=0, lines_removed=0, matched_patterns=())


@dataclass(frozen=True)
class HistoryRecord:
    """Immutable record of AI contribution stats for a single commit.

    One record is appended to the JSONL history file per commit.
    Stored in ~/.claude/ai-herald/history/{repo-identity}.jsonl.
    """

    commit_hash: str
    commit_subject: str
    committed_at: str  # ISO 8601
    branch: str
    author_email: str
    herald_version: str
    files_changed_count: int
    files_ai_touched_count: int
    ai_percentage: float
    ai_lines_added: int
    ai_lines_removed: int
    human_lines_added: int
    human_lines_removed: int
    by_extension: Dict[str, HistoryExtensionStats]
    ignored: HistoryIgnoredStats

    def to_jsonl(self) -> str:
        """Serialize to a single-line JSON string (no trailing newline).

        Returns:
            Compact JSON string suitable for appending to a JSONL file.
        """
        data = {
            'commit_hash': self.commit_hash,
            'commit_subject': self.commit_subject,
            'committed_at': self.committed_at,
            'branch': self.branch,
            'author_email': self.author_email,
            'herald_version': self.herald_version,
            'files_changed_count': self.files_changed_count,
            'files_ai_touched_count': self.files_ai_touched_count,
            'ai_percentage': self.ai_percentage,
            'ai_lines_added': self.ai_lines_added,
            'ai_lines_removed': self.ai_lines_removed,
            'human_lines_added': self.human_lines_added,
            'human_lines_removed': self.human_lines_removed,
            'by_extension': {
                ext: stats.to_dict()
                for ext, stats in self.by_extension.items()
            },
            'ignored': self.ignored.to_dict(),
        }
        return json.dumps(data, separators=(',', ':'))

    @classmethod
    def from_jsonl(cls, line: str) -> 'HistoryRecord':
        """Deserialize from a single JSONL line.

        Args:
            line: A single line from a JSONL history file.

        Returns:
            HistoryRecord instance.

        Raises:
            json.JSONDecodeError: If line is not valid JSON.
            KeyError: If a required field is missing.
        """
        data = json.loads(line.strip())
        ignored_data = data.get('ignored', {
            'total_lines': 0,
            'lines_added': 0,
            'lines_removed': 0,
            'matched_patterns': [],
        })
        return cls(
            commit_hash=data['commit_hash'],
            commit_subject=data['commit_subject'],
            committed_at=data['committed_at'],
            branch=data['branch'],
            author_email=data['author_email'],
            herald_version=data['herald_version'],
            files_changed_count=int(data['files_changed_count']),
            files_ai_touched_count=int(data['files_ai_touched_count']),
            ai_percentage=float(data['ai_percentage']),
            ai_lines_added=int(data['ai_lines_added']),
            ai_lines_removed=int(data['ai_lines_removed']),
            human_lines_added=int(data['human_lines_added']),
            human_lines_removed=int(data['human_lines_removed']),
            by_extension={
                ext: HistoryExtensionStats.from_dict(stats)
                for ext, stats in data.get('by_extension', {}).items()
            },
            ignored=HistoryIgnoredStats.from_dict(ignored_data),
        )
