"""Tests for HookRunner._run_hook() lifecycle."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.hook_runner import HookRunner
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


def _make_provider_mock(enable_logging=False):
    provider = MagicMock(spec=DependencyProvider)
    config = MagicMock()
    config.enable_logging = enable_logging
    provider.config.return_value = config
    return provider


def _make_hook(handler_fn):
    """Create a minimal HookRunner subclass with the given _handle body."""
    class TestHook(HookRunner):
        hook_name = 'TEST'

        def _handle(self, provider, hook_output):
            handler_fn(provider, hook_output)

    return TestHook()


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
            _make_hook(handler).run()

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

        class MyHook(HookRunner):
            hook_name = 'MY-HOOK'

            def _handle(self, provider, hook_output):
                pass

        with pytest.raises(SystemExit):
            MyHook().run()

        mock_provider_cls.assert_called_once_with('MY-HOOK')


class TestRunHookDisabledConfig:

    @patch("infrastructure.hook_runner.HookOutputService")
    @patch("infrastructure.hook_runner.DependencyProvider")
    @patch("infrastructure.hook_runner.ConfigurationLoader")
    def test_handler_not_called_when_disabled(self, mock_loader, mock_provider_cls, mock_output_cls):
        """Given config.enabled is False, handler is never called."""
        mock_loader.resolve_plugin_version.return_value = "0.1"
        mock_output = MagicMock()
        mock_output.exit_with_success.side_effect = SystemExit(0)
        mock_output_cls.return_value = mock_output
        mock_provider = _make_provider_mock(enable_logging=False)
        mock_provider.config.return_value.enabled = False
        mock_provider_cls.return_value = mock_provider

        handler_called = []
        def handler(provider, hook_output):
            handler_called.append(True)

        with pytest.raises(SystemExit) as exc:
            _make_hook(handler).run()

        assert exc.value.code == 0
        assert not handler_called
        mock_output.exit_with_success.assert_called_once_with()


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
            _make_hook(failing_handler).run()

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
            _make_hook(interrupt_handler).run()

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
            _make_hook(early_exit_handler).run()

        assert exc.value.code == 0
        # exit_with_success called once (from handler), not a second time by _run_hook
        mock_output.exit_with_success.assert_called_once_with("early")
