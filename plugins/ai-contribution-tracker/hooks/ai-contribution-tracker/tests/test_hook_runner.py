"""Tests for run_hook() entry-point helper."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.hook_runner import run_hook
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


def _make_provider_mock(enable_logging=False):
    provider = MagicMock(spec=DependencyProvider)
    config = MagicMock()
    config.enable_logging = enable_logging
    provider.config.return_value = config
    return provider


class TestRunHookNormalPath:

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_calls_handler_then_exits(self, mock_loader, mock_provider_cls, mock_output_cls):
        """Given successful handler, calls handler then exit_with_success."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output_cls.return_value = mock_output
        mock_provider = _make_provider_mock()
        mock_provider_cls.return_value = mock_provider

        calls = []
        def handler(provider, hook_output):
            calls.append(('handler', provider, hook_output))

        # exit_with_success raises SystemExit(0)
        mock_output.exit_with_success.side_effect = SystemExit(0)

        with pytest.raises(SystemExit) as exc:
            run_hook('TEST', handler)

        assert exc.value.code == 0
        assert len(calls) == 1
        assert calls[0][0] == 'handler'
        mock_output.exit_with_success.assert_called_once_with()

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_provider_created_with_hook_name(self, mock_loader, mock_provider_cls, mock_output_cls):
        """DependencyProvider is created with the given hook_name."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output.exit_with_success.side_effect = SystemExit(0)
        mock_output_cls.return_value = mock_output
        mock_provider_cls.return_value = _make_provider_mock()

        with pytest.raises(SystemExit):
            run_hook('MY-HOOK', lambda p, o: None)

        mock_provider_cls.assert_called_once_with('MY-HOOK')


class TestRunHookExceptionHandling:

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_exception_in_handler_still_exits_successfully(self, mock_loader, mock_provider_cls, mock_output_cls):
        """Given handler raises Exception, still calls exit_with_success."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output.exit_with_success.side_effect = SystemExit(0)
        mock_output_cls.return_value = mock_output
        mock_provider = _make_provider_mock(enable_logging=False)
        mock_provider_cls.return_value = mock_provider

        def failing_handler(provider, hook_output):
            raise ValueError("something broke")

        with pytest.raises(SystemExit) as exc:
            run_hook('TEST', failing_handler)

        assert exc.value.code == 0
        mock_output.exit_with_success.assert_called_once_with()

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_keyboard_interrupt_not_swallowed(self, mock_loader, mock_provider_cls, mock_output_cls):
        """KeyboardInterrupt propagates instead of being swallowed."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output_cls.return_value = mock_output
        mock_provider = _make_provider_mock()
        mock_provider_cls.return_value = mock_provider

        def interrupt_handler(provider, hook_output):
            raise KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            run_hook('TEST', interrupt_handler)

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_system_exit_from_handler_propagates(self, mock_loader, mock_provider_cls, mock_output_cls):
        """SystemExit raised inside handler (early exit) propagates correctly."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output.exit_with_success.side_effect = SystemExit(0)
        mock_output_cls.return_value = mock_output
        mock_provider = _make_provider_mock()
        mock_provider_cls.return_value = mock_provider

        def early_exit_handler(provider, hook_output):
            hook_output.exit_with_success("early")

        with pytest.raises(SystemExit) as exc:
            run_hook('TEST', early_exit_handler)

        assert exc.value.code == 0
        # exit_with_success called once (from handler), not a second time by run_hook
        mock_output.exit_with_success.assert_called_once_with("early")
