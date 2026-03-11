"""Service for querying and rendering AI contribution history."""

import json
import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from domain.history_record import HistoryRecord
from infrastructure.configuration import Configuration
from infrastructure.history_repository import HistoryRepository


_HISTORY_DISABLED_MSG = (
    "History tracking is not enabled. Add this to ~/.claude/ai-herald/config.json:\n"
    "\n"
    '  "history": {\n'
    '    "enabled": true\n'
    "  }\n"
    "\n"
    "Then make commits to start building your history."
)


def _parse_since(since: str) -> Optional[datetime]:
    """Parse a --since argument into a UTC-aware datetime lower bound.

    Accepts: '30d', '4w', '3m' (relative), 'YYYY-MM-DD' (absolute).
    Returns None for unrecognised input.
    """
    now = datetime.now(tz=timezone.utc)
    m = re.fullmatch(r'(\d+)(d|w|m)', since.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == 'd':
            return now - timedelta(days=n)
        elif unit == 'w':
            return now - timedelta(weeks=n)
        else:  # 'm'
            return now - timedelta(days=n * 30)
    try:
        dt = datetime.fromisoformat(since.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_committed_at(committed_at: str) -> datetime:
    """Parse ISO 8601 committed_at string to a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(committed_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _period_key(record: HistoryRecord, by: str) -> str:
    """Derive grouping key for a record."""
    dt = _parse_committed_at(record.committed_at)
    if by == 'month':
        return dt.strftime('%Y-%m')
    elif by == 'commit':
        return record.commit_hash
    else:  # week (default)
        d = dt.date()
        monday = d - timedelta(days=d.weekday())
        return monday.isoformat()


def _aggregate(records: List[HistoryRecord], period: str) -> Dict:
    """Aggregate a list of records into a single group dict."""
    total_weight = sum(
        r.ai_lines_added + r.ai_lines_removed + r.human_lines_added + r.human_lines_removed
        for r in records
    )
    if total_weight > 0:
        weighted_pct = sum(
            r.ai_percentage
            * (r.ai_lines_added + r.ai_lines_removed + r.human_lines_added + r.human_lines_removed)
            for r in records
        ) / total_weight
    else:
        weighted_pct = sum(r.ai_percentage for r in records) / len(records)

    seen: set = set()
    unique_patterns: List[str] = []
    for r in records:
        for p in sorted(r.ignored.matched_patterns):
            if p not in seen:
                seen.add(p)
                unique_patterns.append(p)

    first = records[0]
    return {
        'period': period,
        'commits': len(records),
        'ai_percentage': round(weighted_pct, 1),
        'ai_lines_added': sum(r.ai_lines_added for r in records),
        'ai_lines_removed': sum(r.ai_lines_removed for r in records),
        'human_lines_added': sum(r.human_lines_added for r in records),
        'human_lines_removed': sum(r.human_lines_removed for r in records),
        'ignored_lines': sum(r.ignored.total_lines for r in records),
        'ignored_patterns': sorted(unique_patterns),
        # Commit-view extras (populated when len(records)==1)
        '_date': _parse_committed_at(first.committed_at).strftime('%Y-%m-%d'),
        '_hash': first.commit_hash[:8] if len(records) == 1 else '',
        '_subject': first.commit_subject if len(records) == 1 else '',
    }


def _ignored_cell(group: Dict) -> str:
    """Format the Ignored column cell."""
    n = group['ignored_lines']
    if n == 0:
        return '0 lines'
    patterns = group['ignored_patterns']
    if patterns:
        pats = ', '.join(patterns)
        return f"{n} lines ({pats})"
    return f"{n} lines"


def _render_table(aggregates: List[Dict], by: str, identity: str, total_commits: int) -> str:
    lines = [f"AI Contribution History — {identity}", ""]

    if by == 'commit':
        header = f"{'Date':<12}  {'Hash':<8}  {'AI%':<6}  {'Added':<22}  {'Removed':<20}  Ignored"
        lines.append(header)
        lines.append("-" * len(header))
        for g in aggregates:
            total_added = g['ai_lines_added'] + g['human_lines_added']
            total_removed = g['ai_lines_removed'] + g['human_lines_removed']
            added_str = f"+{total_added} / +{g['ai_lines_added']} AI"
            removed_str = f"-{total_removed} / -{g['ai_lines_removed']} AI"
            pct_str = f"{g['ai_percentage']:.0f}%"
            lines.append(
                f"{g['_date']:<12}  {g['_hash']:<8}  {pct_str:<6}  "
                f"{added_str:<22}  {removed_str:<20}  {_ignored_cell(g)}"
            )
    else:
        period_label = "Week" if by == 'week' else "Month"
        header = f"{period_label:<12}  {'Commits':<7}  {'AI%':<6}  {'Added':<22}  {'Removed':<20}  Ignored"
        lines.append(header)
        lines.append("-" * len(header))
        for g in aggregates:
            total_added = g['ai_lines_added'] + g['human_lines_added']
            total_removed = g['ai_lines_removed'] + g['human_lines_removed']
            added_str = f"+{total_added} / +{g['ai_lines_added']} AI"
            removed_str = f"-{total_removed} / -{g['ai_lines_removed']} AI"
            pct_str = f"{g['ai_percentage']:.0f}%"
            lines.append(
                f"{g['period']:<12}  {g['commits']:<7}  {pct_str:<6}  "
                f"{added_str:<22}  {removed_str:<20}  {_ignored_cell(g)}"
            )

    lines.append("")
    all_pcts = [g['ai_percentage'] for g in aggregates]
    avg_pct = sum(all_pcts) / len(all_pcts)

    if len(aggregates) >= 2:
        delta = aggregates[-1]['ai_percentage'] - aggregates[0]['ai_percentage']
        if delta > 0:
            trend_arrow = f"▲ +{delta:.0f}pp"
        elif delta < 0:
            trend_arrow = f"▼ {delta:.0f}pp"
        else:
            trend_arrow = "→ 0pp"
        n = len(aggregates)
        unit = "commits" if by == 'commit' else f"{by}s"
        trend_str = f"Trend: {trend_arrow} over {n} {unit}"
    else:
        trend_str = "Trend: single period"

    lines.append(f"{trend_str}  |  Total: {total_commits} commits  |  Avg AI%: {avg_pct:.0f}%")
    return "\n".join(lines)


def _render_json(aggregates: List[Dict]) -> str:
    public = [
        {
            'period': g['period'],
            'commits': g['commits'],
            'ai_percentage': g['ai_percentage'],
            'ai_lines_added': g['ai_lines_added'],
            'human_lines_added': g['human_lines_added'],
            'ai_lines_removed': g['ai_lines_removed'],
            'human_lines_removed': g['human_lines_removed'],
            'ignored_lines': g['ignored_lines'],
            'ignored_patterns': g['ignored_patterns'],
        }
        for g in aggregates
    ]
    return json.dumps(public, indent=2)


def _render_csv(aggregates: List[Dict]) -> str:
    rows = ['period,commits,ai_percentage,ai_lines_added,human_lines_added,'
            'ai_lines_removed,human_lines_removed,ignored_lines']
    for g in aggregates:
        rows.append(
            f"{g['period']},{g['commits']},{g['ai_percentage']},"
            f"{g['ai_lines_added']},{g['human_lines_added']},"
            f"{g['ai_lines_removed']},{g['human_lines_removed']},"
            f"{g['ignored_lines']}"
        )
    return "\n".join(rows)


class HistoryQueryService:
    """Reads, filters, groups, and renders AI contribution history.

    Supports grouping by week, month, or individual commit.
    Produces table, JSON, or CSV output.
    """

    def __init__(self, history_repo: HistoryRepository, config: Configuration):
        """Initialize the service.

        Args:
            history_repo: HistoryRepository for reading records.
            config: Configuration (used for history_enabled guard).
        """
        self._history_repo = history_repo
        self._config = config

    def query(
        self,
        since: Optional[str] = None,
        by: str = 'week',
        author: Optional[str] = None,
        output_format: str = 'table',
    ) -> str:
        """Query history records and return formatted output.

        Args:
            since: Optional time filter ('30d', '4w', '3m', 'YYYY-MM-DD').
            by: Grouping period ('week', 'month', 'commit').
            author: Optional author email filter.
            output_format: Output format ('table', 'json', 'csv').

        Returns:
            Formatted string ready to print.
        """
        history_exists = self._history_repo.file_path.exists()
        if not self._config.history_enabled and not history_exists:
            return _HISTORY_DISABLED_MSG

        records = self._history_repo.read_all()

        if not records:
            if not self._config.history_enabled:
                return _HISTORY_DISABLED_MSG
            return "No history records found. Make commits with history.enabled=true to start."

        # Filter by since
        since_dt = _parse_since(since) if since else None
        if since_dt:
            records = [r for r in records if _parse_committed_at(r.committed_at) >= since_dt]

        # Filter by author
        if author:
            records = [r for r in records if r.author_email == author]

        if not records:
            return "No records match the specified filters."

        # Sort chronologically before dedup (ascending → last iteration = most recent)
        records.sort(key=lambda r: _parse_committed_at(r.committed_at))

        # Deduplicate by branch: cumulative stats mean only the latest record is meaningful
        branch_latest: dict = {}
        for r in records:
            branch_latest[r.branch] = r  # ascending sort → last write = most recent
        records = sorted(branch_latest.values(), key=lambda r: _parse_committed_at(r.committed_at))

        # Group
        groups_map: OrderedDict = OrderedDict()
        for r in records:
            key = _period_key(r, by)
            groups_map.setdefault(key, []).append(r)

        aggregates = [_aggregate(recs, period) for period, recs in groups_map.items()]

        if output_format == 'json':
            return _render_json(aggregates)
        elif output_format == 'csv':
            return _render_csv(aggregates)
        else:
            return _render_table(aggregates, by, self._history_repo.repo_identity, len(records))
