"""Tests for herald-pre-writer.py hook."""

import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


def _load_hook_module():
    """Load herald-pre-writer.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / 'herald-pre-writer.py'
    spec = importlib.util.spec_from_file_location('herald_pre_writer', hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_stdin(tool_input: dict) -> io.StringIO:
    return io.StringIO(json.dumps({'tool_input': tool_input}))


def _make_provider_and_output():
    provider = MagicMock(spec=DependencyProvider)
    hook_output = MagicMock(spec=HookOutputService)
    hook_output.exit_with_success.side_effect = SystemExit(0)

    capture_service = MagicMock()
    provider.build_capture_service.return_value = capture_service

    return provider, hook_output, capture_service


class TestHandleMissingFilePath:
    """Tests for _handle when file_path is absent or empty."""

    def test_missing_file_path_exits_early(self):
        """Given no file_path in tool_input, _handle calls exit_with_success."""
        module = _load_hook_module()
        provider, hook_output, capture_service = _make_provider_and_output()

        with patch('sys.stdin', _make_stdin({})):
            with pytest.raises(SystemExit) as exc:
                module.PreWriterHook()._handle(provider, hook_output)

        assert exc.value.code == 0
        capture_service.store_pre_write_snapshot.assert_not_called()

    def test_empty_file_path_exits_early(self):
        """Given empty file_path, _handle calls exit_with_success."""
        module = _load_hook_module()
        provider, hook_output, capture_service = _make_provider_and_output()

        with patch('sys.stdin', _make_stdin({'file_path': ''})):
            with pytest.raises(SystemExit) as exc:
                module.PreWriterHook()._handle(provider, hook_output)

        assert exc.value.code == 0
        capture_service.store_pre_write_snapshot.assert_not_called()


class TestHandleWithFilePath:
    """Tests for _handle when a valid file_path is provided."""

    def test_calls_store_pre_write_snapshot_with_file_path(self):
        """Given a valid file_path, store_pre_write_snapshot is called."""
        module = _load_hook_module()
        provider, hook_output, capture_service = _make_provider_and_output()
        file_path = '/project/src/app.py'

        with patch('sys.stdin', _make_stdin({'file_path': file_path})):
            module.PreWriterHook()._handle(provider, hook_output)

        capture_service.store_pre_write_snapshot.assert_called_once_with(file_path)

    def test_build_capture_service_called_once(self):
        """Given a valid file_path, build_capture_service is called to get the service."""
        module = _load_hook_module()
        provider, hook_output, capture_service = _make_provider_and_output()

        with patch('sys.stdin', _make_stdin({'file_path': '/project/app.py'})):
            module.PreWriterHook()._handle(provider, hook_output)

        provider.build_capture_service.assert_called_once()


class TestMainIntegration:
    """Integration tests for the main() entry point via run_hook."""

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_main_exits_successfully_with_valid_input(
        self, mock_loader, mock_provider_cls, mock_output_cls
    ):
        """main() completes without error given valid file_path input."""
        module = _load_hook_module()

        mock_loader.resolve_plugin_version.return_value = "0.0.5"
        mock_output = MagicMock()
        mock_output.exit_with_success.side_effect = SystemExit(0)
        mock_output_cls.return_value = mock_output

        mock_provider = MagicMock(spec=DependencyProvider)
        config = MagicMock()
        config.enabled = True
        mock_provider.config.return_value = config
        capture_service = MagicMock()
        mock_provider.build_capture_service.return_value = capture_service
        mock_provider_cls.return_value = mock_provider

        with patch('sys.stdin', _make_stdin({'file_path': '/project/app.py'})):
            with pytest.raises(SystemExit) as exc:
                module.main()

        assert exc.value.code == 0
        capture_service.store_pre_write_snapshot.assert_called_once_with('/project/app.py')
