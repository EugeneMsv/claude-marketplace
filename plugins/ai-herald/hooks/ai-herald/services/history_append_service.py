"""Service for appending per-commit history records."""

from datetime import datetime, timezone
from logging import Logger
from typing import Optional

from domain.contribution_stats import ContributionStats
from domain.history_record import HistoryExtensionStats, HistoryIgnoredStats, HistoryRecord
from domain.tracking_data import TrackingData
from infrastructure.configuration import Configuration, ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.history_repository import HistoryRepository


class HistoryAppendService:
    """Assembles and persists a HistoryRecord after each successful inject.

    Reads commit metadata from git, maps ContributionStats fields into
    the history schema, and delegates to HistoryRepository for storage.
    All errors are caught and logged — this service must never raise.
    """

    def __init__(
        self,
        git_repo: GitRepository,
        history_repo: HistoryRepository,
        config: Configuration,
        logger: Logger,
    ):
        """Initialize the service.

        Args:
            git_repo: GitRepository for reading commit metadata.
            history_repo: HistoryRepository for appending records.
            config: Configuration (used for history_enabled guard).
            logger: Logger instance.
        """
        self._git_repo = git_repo
        self._history_repo = history_repo
        self._config = config
        self._logger = logger

    def append_commit(self, stats: ContributionStats, tracking: TrackingData) -> None:
        """Assemble a HistoryRecord from stats and persist it.

        No-op when history is disabled in config. Logs and swallows all
        exceptions so a history failure never breaks the inject hook.

        Args:
            stats: ContributionStats computed during inject.
            tracking: TrackingData used during inject (provides merge_base,
                      files_tracked, and branch).
        """
        if not self._config.history_enabled:
            return

        try:
            self._do_append(stats, tracking)
        except Exception as e:
            self._logger.warning(f"History append failed: {e}")

    def _do_append(self, stats: ContributionStats, tracking: TrackingData) -> None:
        """Internal: gather git metadata, build record, and persist."""
        commit_hash = self._git_repo.get_head_commit_hash()
        if not commit_hash:
            self._logger.warning("History: could not read HEAD commit hash — skipping")
            return

        commit_subject = self._git_repo.get_head_commit_subject() or ""
        committed_at = self._git_repo.get_head_commit_timestamp() or _utc_now_iso()
        author_email = self._git_repo.get_author_email() or ""
        herald_version = ConfigurationLoader.resolve_plugin_version()

        files_changed_count = (
            self._git_repo.get_changed_file_count(tracking.merge_base)
            if tracking.merge_base
            else 0
        )
        files_ai_touched_count = len(tracking.files_tracked) if tracking.files_tracked else 0

        by_extension = {
            ext: HistoryExtensionStats(
                ai_percentage=ft.ai_percentage,
                ai_lines=ft.ai_lines,
                human_lines=ft.human_lines,
            )
            for ext, ft in stats.by_file_type.items()
        }

        ig = stats.ignored_files
        ignored = HistoryIgnoredStats(
            total_lines=ig.total,
            lines_added=ig.added,
            lines_removed=ig.removed,
            matched_patterns=tuple(sorted(ig.matched_patterns)),
        )

        record = HistoryRecord(
            commit_hash=commit_hash,
            commit_subject=commit_subject,
            committed_at=committed_at,
            branch=tracking.branch,
            author_email=author_email,
            herald_version=herald_version,
            files_changed_count=files_changed_count,
            files_ai_touched_count=files_ai_touched_count,
            ai_percentage=stats.ai_percentage,
            ai_lines_added=stats.ai_stats.added.lines,
            ai_lines_removed=stats.ai_stats.removed.lines,
            human_lines_added=stats.human_stats.added.lines,
            human_lines_removed=stats.human_stats.removed.lines,
            by_extension=by_extension,
            ignored=ignored,
        )

        self._history_repo.append(record)
        self._logger.info(f"History: appended record for {commit_hash[:8]}")


def _utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format as fallback."""
    return datetime.now(tz=timezone.utc).isoformat()
