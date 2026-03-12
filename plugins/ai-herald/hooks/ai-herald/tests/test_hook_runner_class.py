"""Tests for HookRunner and CommandHookRunner classes."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.hook_runner import CommandHookRunner, HookRunner
from services.bash_command_detector import DetectedCommand


def _make_stdin(command: str) -> StringIO:
    return StringIO(json.dumps({"tool_input": {"command": command}}))


def _make_provider(ordered=None, detected_set=None):
    """Build a mock provider with a configured bash_command_detector."""
    provider = MagicMock()
    detector = MagicMock()
    detector.detect_commands_ordered.return_value = ordered or []
    detector.detect_commands.return_value = set(detected_set) if detected_set else {DetectedCommand.UNIDENTIFIED}
    provider.bash_command_detector.return_value = detector
    return provider


def _make_hook_output():
    hook_output = MagicMock()
    hook_output.exit_with_success.side_effect = SystemExit(0)
    return hook_output


class TestCommandHookRunnerNoMatch:
    """No matching command → exit_with_success, no handlers called."""

    def test_no_match_exits_early_and_skips_handlers(self):
        handler = MagicMock(return_value=None)

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {DetectedCommand.GIT_COMMIT: handler}

        provider = _make_provider(
            ordered=[DetectedCommand.GIT_PUSH],
            detected_set={DetectedCommand.GIT_PUSH},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('git push')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        handler.assert_not_called()
        hook_output.exit_with_success.assert_called_once_with()


class TestCommandHookRunnerSingleMatch:
    """Single match → handler called with (provider, command), result to on_result."""

    def test_single_match_calls_handler_and_on_result(self):
        expected_result = object()
        handler = MagicMock(return_value=expected_result)
        on_result_args = []

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {DetectedCommand.GIT_COMMIT: handler}

            def on_result(self, provider, hook_output, result):
                on_result_args.append(result)
                hook_output.exit_with_success()

        command = 'git commit -m "msg"'
        provider = _make_provider(
            ordered=[DetectedCommand.GIT_COMMIT],
            detected_set={DetectedCommand.GIT_COMMIT},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin(command)):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        handler.assert_called_once_with(ANY, provider, command)
        assert on_result_args == [expected_result]


class TestCommandHookRunnerMultiMatch:
    """Multi-match ordered → all handlers in detection order, last non-None result kept."""

    def test_multi_match_dispatches_in_order_last_result_kept(self):
        call_order = []
        result_a = object()
        result_b = object()

        def handler_a(self, provider, command):
            call_order.append('A')
            return result_a

        def handler_b(self, provider, command):
            call_order.append('B')
            return result_b

        on_result_args = []

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {
                DetectedCommand.GIT_MERGE: handler_a,
                DetectedCommand.GIT_COMMIT: handler_b,
            }

            def on_result(self, provider, hook_output, result):
                on_result_args.append(result)
                hook_output.exit_with_success()

        # Ordered: merge first, then commit (as they appear in command string)
        provider = _make_provider(
            ordered=[DetectedCommand.GIT_MERGE, DetectedCommand.GIT_COMMIT],
            detected_set={DetectedCommand.GIT_MERGE, DetectedCommand.GIT_COMMIT},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('git merge main && git commit -m "fix"')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        assert call_order == ['A', 'B']
        # Last non-None result (result_b from handler_b) is passed to on_result
        assert on_result_args == [result_b]

    def test_none_results_do_not_overwrite_previous(self):
        """Handler returning None doesn't overwrite a previous non-None result."""
        result_a = object()

        def handler_a(self, provider, command):
            return result_a

        def handler_b(self, provider, command):
            return None  # no-op handler

        on_result_args = []

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {
                DetectedCommand.GIT_COMMIT: handler_a,
                DetectedCommand.GIT_MERGE: handler_b,
            }

            def on_result(self, provider, hook_output, result):
                on_result_args.append(result)
                hook_output.exit_with_success()

        provider = _make_provider(
            ordered=[DetectedCommand.GIT_COMMIT, DetectedCommand.GIT_MERGE],
            detected_set={DetectedCommand.GIT_COMMIT, DetectedCommand.GIT_MERGE},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('git commit -m "x" && git merge main')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        assert on_result_args == [result_a]


class TestCommandHookRunnerDefaultOnResult:
    """Default on_result → exit_with_success() with no message."""

    def test_default_on_result_exits_with_no_message(self):
        handler = MagicMock(return_value=None)

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {DetectedCommand.GIT_COMMIT: handler}

        provider = _make_provider(
            ordered=[DetectedCommand.GIT_COMMIT],
            detected_set={DetectedCommand.GIT_COMMIT},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('git commit -m "msg"')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        hook_output.exit_with_success.assert_called_once_with()


class TestCommandHookRunnerOverriddenOnResult:
    """Overridden on_result → called with the correct result."""

    def test_overridden_on_result_receives_correct_result(self):
        my_result = {'key': 'value'}
        handler = MagicMock(return_value=my_result)
        received = []

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {DetectedCommand.GIT_COMMIT: handler}

            def on_result(self, provider, hook_output, result):
                received.append(result)
                hook_output.exit_with_success('custom message')

        provider = _make_provider(
            ordered=[DetectedCommand.GIT_COMMIT],
            detected_set={DetectedCommand.GIT_COMMIT},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('git commit -m "msg"')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        assert received == [my_result]
        hook_output.exit_with_success.assert_called_once_with('custom message')


class TestCommandHookRunnerNonOrderedCommands:
    """Non-position-ordered commands (CODE_FORMATTER, BASH_FILE_DELETION) are detected via set supplement."""

    def test_non_ordered_command_dispatched_when_in_detect_set(self):
        handler = MagicMock(return_value='snapshot_path')
        on_result_args = []

        class TestHook(CommandHookRunner):
            hook_name = 'TEST'
            command_handlers = {DetectedCommand.CODE_FORMATTER: handler}

            def on_result(self, provider, hook_output, result):
                on_result_args.append(result)
                hook_output.exit_with_success()

        provider = _make_provider(
            ordered=[],  # CODE_FORMATTER not in ordered
            detected_set={DetectedCommand.CODE_FORMATTER},
        )
        hook_output = _make_hook_output()

        with patch('sys.stdin', _make_stdin('./gradlew spotlessApply')):
            with pytest.raises(SystemExit):
                TestHook()._handle(provider, hook_output)

        handler.assert_called_once()
        assert on_result_args == ['snapshot_path']
