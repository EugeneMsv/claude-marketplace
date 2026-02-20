"""Tests for DependencyProvider."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.configuration import Configuration
from services.bash_command_detector import BashCommandDetector
from services.capture_service import CaptureService
from services.inject_service import InjectService
from services.mr_service import MrService
from services.format_snapshot_service import FormatSnapshotService
from services.format_tracker_service import FormatTrackerService
from services.housekeeping_service import HousekeepingService


def _make_config(enabled: bool = True) -> Configuration:
    return Configuration(
        enabled=enabled,
        base_branches=["main"],
        tracked_extensions={".py"},
        enable_logging=False,
        log_file="test.log",
        format_commands=["spotlessApply"],
    )


class TestLazyProperties:

    @patch("infrastructure.dependency_provider.ConfigurationLoader.load")
    def test_config_loaded_once(self, mock_load):
        """config() loads configuration exactly once and caches it."""
        mock_load.return_value = _make_config()
        provider = DependencyProvider("TEST")

        cfg1 = provider.config()
        cfg2 = provider.config()

        assert cfg1 is cfg2
        mock_load.assert_called_once()

    @patch("infrastructure.dependency_provider.ConfigurationLoader.resolve_log_path", return_value=Path("/tmp/test.log"))
    @patch("infrastructure.dependency_provider.ConfigurationLoader.load")
    @patch("infrastructure.dependency_provider.setup_hook_logger")
    def test_logger_set_up_once(self, mock_setup, mock_load, mock_log_path):
        """logger() sets up the logger exactly once and caches it."""
        mock_load.return_value = _make_config()
        mock_logger = MagicMock()
        mock_setup.return_value = (mock_logger, "abc12345")
        provider = DependencyProvider("TEST")

        l1 = provider.logger()
        l2 = provider.logger()

        assert l1 is l2
        mock_setup.assert_called_once_with("TEST", Path("/tmp/test.log"), False)

    @patch("infrastructure.dependency_provider.ConfigurationLoader.resolve_log_path", return_value=Path("/tmp/test.log"))
    @patch("infrastructure.dependency_provider.ConfigurationLoader.load")
    @patch("infrastructure.dependency_provider.setup_hook_logger")
    def test_git_repo_created_once(self, mock_setup, mock_load, _):
        """git_repo() creates GitRepository exactly once and caches it."""
        mock_load.return_value = _make_config()
        mock_setup.return_value = (MagicMock(), "trace")
        provider = DependencyProvider("TEST")

        with patch("infrastructure.dependency_provider.GitRepository") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            r1 = provider.git_repo()
            r2 = provider.git_repo()

        assert r1 is r2
        mock_cls.assert_called_once()

    @patch("infrastructure.dependency_provider.ConfigurationLoader.resolve_log_path", return_value=Path("/tmp/test.log"))
    @patch("infrastructure.dependency_provider.ConfigurationLoader.load")
    @patch("infrastructure.dependency_provider.setup_hook_logger")
    def test_glab_repo_not_cached(self, mock_setup, mock_load, _):
        """glab_repo() returns a new instance each call (not cached)."""
        mock_load.return_value = _make_config()
        mock_setup.return_value = (MagicMock(), "trace")
        provider = DependencyProvider("TEST")

        with patch("infrastructure.dependency_provider.GlabRepository") as mock_cls:
            mock_cls.side_effect = lambda logger: MagicMock()

            r1 = provider.glab_repo()
            r2 = provider.glab_repo()

        assert r1 is not r2
        assert mock_cls.call_count == 2


class TestServiceBuilders:

    def _make_provider(self, format_commands=None):
        config = _make_config()
        if format_commands is not None:
            config = Configuration(
                enabled=True,
                base_branches=["main"],
                tracked_extensions={".py"},
                enable_logging=False,
                log_file="test.log",
                format_commands=format_commands,
            )
        provider = DependencyProvider("TEST")
        provider._config = config

        import logging
        from infrastructure.hook_logger import HookLoggerAdapter
        base_logger = logging.getLogger("test")
        provider._logger = HookLoggerAdapter(base_logger, {"hook_name": "TEST", "trace_id": "abc"})
        provider._trace_id = "abc"
        provider._git_repo = MagicMock()

        return provider

    def test_bash_command_detector_returns_correct_type(self):
        """bash_command_detector() returns a BashCommandDetector."""
        provider = self._make_provider()
        result = provider.bash_command_detector()
        assert isinstance(result, BashCommandDetector)

    def test_bash_command_detector_cached(self):
        """bash_command_detector() returns the same instance on repeated calls."""
        provider = self._make_provider()
        d1 = provider.bash_command_detector()
        d2 = provider.bash_command_detector()
        assert d1 is d2

    def test_build_capture_service_returns_correct_type(self):
        """build_capture_service() returns a CaptureService."""
        provider = self._make_provider()
        result = provider.build_capture_service()
        assert isinstance(result, CaptureService)

    def test_build_inject_service_returns_correct_type(self):
        """build_inject_service() returns an InjectService."""
        provider = self._make_provider()
        result = provider.build_inject_service()
        assert isinstance(result, InjectService)

    def test_build_mr_service_returns_correct_type(self):
        """build_mr_service() returns an MrService."""
        provider = self._make_provider()
        with patch("infrastructure.dependency_provider.GlabRepository"):
            result = provider.build_mr_service()
        assert isinstance(result, MrService)

    def test_build_format_snapshot_service_returns_correct_type(self):
        """build_format_snapshot_service() returns a FormatSnapshotService."""
        provider = self._make_provider()
        result = provider.build_format_snapshot_service()
        assert isinstance(result, FormatSnapshotService)

    def test_build_format_tracker_service_returns_correct_type(self):
        """build_format_tracker_service() returns a FormatTrackerService."""
        provider = self._make_provider()
        result = provider.build_format_tracker_service()
        assert isinstance(result, FormatTrackerService)

    def test_build_housekeeping_service_returns_correct_type(self):
        """build_housekeeping_service() returns a HousekeepingService."""
        provider = self._make_provider()
        result = provider.build_housekeeping_service()
        assert isinstance(result, HousekeepingService)
