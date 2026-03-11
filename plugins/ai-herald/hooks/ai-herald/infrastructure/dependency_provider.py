"""Centralized lazy service factory for AI contribution tracker hooks."""

from __future__ import annotations

from logging import Logger
from pathlib import Path
from typing import Optional

from infrastructure.configuration import Configuration, ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.glab_repository import GlabRepository
from infrastructure.hook_logger import setup_hook_logger


class DependencyProvider:
    """Centralized, lazy dependency factory for hook entry points.

    Created once per hook invocation with the hook's log-prefix name.
    Config, logger, git_repo, and bash_command_detector are cached (created on first access).
    GlabRepository is not cached since it wraps the logger.

    Usage:
        provider = DependencyProvider('CAPTURE')
        if not provider.config().enabled:
            hook_output.exit_with_success()
        service = provider.build_capture_service()
    """

    def __init__(self, hook_name: str):
        """Initialize provider for the given hook.

        Args:
            hook_name: Hook identifier used as logger prefix (e.g. 'CAPTURE', 'INJECT')
        """
        self._hook_name = hook_name
        self._config: Optional[Configuration] = None
        self._logger: Optional[Logger] = None
        self._trace_id: Optional[str] = None
        self._git_repo: Optional[GitRepository] = None
        self._detector = None
        self._deletion_targets_detector = None
        self._ignored_files_detector = None

    def config(self) -> Configuration:
        """Return cached Configuration, loading it on first call."""
        if self._config is None:
            self._config = ConfigurationLoader.load()
        return self._config

    def logger(self) -> Logger:
        """Return cached logger adapter, setting it up on first call."""
        if self._logger is None:
            log_path = ConfigurationLoader.resolve_log_path(self.config())
            self._logger, self._trace_id = setup_hook_logger(
                self._hook_name, log_path, self.config().enable_logging
            )
        return self._logger

    def trace_id(self) -> Optional[str]:
        """Return trace ID (available after first logger() call)."""
        if self._trace_id is None:
            self.logger()  # triggers setup
        return self._trace_id

    def git_repo(self) -> GitRepository:
        """Return cached GitRepository instance."""
        if self._git_repo is None:
            self._git_repo = GitRepository()
        return self._git_repo

    def glab_repo(self) -> GlabRepository:
        """Return a new GlabRepository wrapping the current logger (not cached)."""
        return GlabRepository(self.logger())

    def bash_command_detector(self) -> BashCommandDetector:
        """Return cached BashCommandDetector configured from current config."""
        if self._detector is None:
            from services.bash_command_detector import BashCommandDetector
            self._detector = BashCommandDetector(self.config())
        return self._detector

    def deletion_targets_detector(self) -> 'DeletionTargetsDetector':
        """Return cached DeletionTargetsDetector."""
        if self._deletion_targets_detector is None:
            from services.deletion_targets_detector import DeletionTargetsDetector
            self._deletion_targets_detector = DeletionTargetsDetector()
        return self._deletion_targets_detector

    def ignored_files_detector(self) -> 'IgnoredFilesDetector':
        """Return cached IgnoredFilesDetector configured from current config."""
        if self._ignored_files_detector is None:
            from domain.ignored_files_detector import IgnoredFilesDetector
            self._ignored_files_detector = IgnoredFilesDetector(self.config().ignored_paths)
        return self._ignored_files_detector

    # --- Service builders ---

    def build_write_snapshot_repo(self) -> WriteSnapshotRepository:
        """Build and return a WriteSnapshotRepository for the current git root.

        Returns a repository wired to the project's .claude/write-snapshots/
        directory. If git root is unavailable, the repository's methods are
        safe no-ops (save returns False, load_and_delete returns '').
        """
        from infrastructure.write_snapshot_repository import WriteSnapshotRepository
        return WriteSnapshotRepository(self.git_repo().get_root())

    def build_capture_service(self) -> CaptureService:
        """Build and return a fully-wired CaptureService."""
        from domain.line_hasher import LineHasher
        from services.capture_service import CaptureService
        return CaptureService(
            self.git_repo(), self.config(), LineHasher(), self.logger(),
            self.build_write_snapshot_repo(), self.ignored_files_detector()
        )

    def build_inject_service(self) -> InjectService:
        """Build and return a fully-wired InjectService."""
        from domain.line_hasher import LineHasher
        from services.stats_calculator import StatsCalculator
        from services.inject_service import InjectService
        hasher = LineHasher()
        stats_calculator = StatsCalculator(hasher, self.config().tracked_extensions, self.ignored_files_detector())
        return InjectService(self.git_repo(), self.config(), stats_calculator, self.logger())

    def build_mr_service(self) -> MrService:
        """Build and return a fully-wired MrService."""
        from services.mr_service import MrService
        return MrService(self.git_repo(), self.glab_repo(), self.config(), self.logger())

    def build_format_snapshot_service(self) -> FormatSnapshotService:
        """Build and return a fully-wired FormatSnapshotService."""
        from domain.line_hasher import LineHasher
        from services.format_snapshot_service import FormatSnapshotService
        return FormatSnapshotService(self.git_repo(), self.config(), LineHasher(), self.logger())

    def build_format_tracker_service(self) -> FormatTrackerService:
        """Build and return a fully-wired FormatTrackerService."""
        from domain.line_hasher import LineHasher
        from domain.token_normalizer import TokenNormalizer
        from services.format_tracker_service import FormatTrackerService
        return FormatTrackerService(self.git_repo(), self.config(), LineHasher(), TokenNormalizer(), self.logger())

    def build_housekeeping_service(self) -> HousekeepingService:
        """Build and return a fully-wired HousekeepingService."""
        from services.housekeeping_service import HousekeepingService
        return HousekeepingService(self.git_repo(), self.config(), self.logger())

    def build_deletion_tracker_service(self) -> 'DeletionTrackerService':
        """Build and return a fully-wired DeletionTrackerService."""
        from services.deletion_tracker_service import DeletionTrackerService
        return DeletionTrackerService(
            self.git_repo(), self.config(), self.logger()
        )

    def build_query_stats_service(self) -> 'QueryStatsService':
        """Build and return a fully-wired QueryStatsService."""
        from domain.line_hasher import LineHasher
        from services.stats_calculator import StatsCalculator
        from services.query.query_stats_service import QueryStatsService
        hasher = LineHasher()
        stats_calculator = StatsCalculator(hasher, self.config().tracked_extensions, self.ignored_files_detector())
        return QueryStatsService(self.git_repo(), self.config(), stats_calculator, self.logger())

    def build_history_append_service(self) -> 'HistoryAppendService':
        """Build and return a fully-wired HistoryAppendService."""
        from infrastructure.history_repository import HistoryRepository
        from services.history_append_service import HistoryAppendService
        history_repo = HistoryRepository(self.git_repo())
        return HistoryAppendService(self.git_repo(), history_repo, self.config(), self.logger())

    def build_history_query_service(self) -> 'HistoryQueryService':
        """Build and return a fully-wired HistoryQueryService."""
        from infrastructure.history_repository import HistoryRepository
        from services.query.history_query_service import HistoryQueryService
        history_repo = HistoryRepository(self.git_repo())
        return HistoryQueryService(history_repo, self.config())
