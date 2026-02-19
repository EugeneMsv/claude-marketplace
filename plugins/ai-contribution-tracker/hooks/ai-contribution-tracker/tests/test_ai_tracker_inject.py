"""Tests for ai-tracker-inject.py routing logic."""

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))

from services.inject_service import InjectResult


def _make_hook_input(command: str) -> str:
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command}
    })


def _make_config(enabled: bool = True):
    from infrastructure.configuration import Configuration
    return Configuration(
        enabled=enabled,
        base_branches=["main"],
        tracked_extensions={".py"},
        enable_logging=False,
        log_file="test.log",
    )


def _run_main(command: str, enabled: bool = True):
    """Run hook main() with mocked stdin and patched dependencies.

    Returns the mock InjectService so callers can assert on it.
    """
    mock_service = MagicMock()
    mock_service.process_commit.return_value = InjectResult(False)
    mock_service.recover_missed_commit.return_value = InjectResult(False)

    config = _make_config(enabled)

    with patch("sys.stdin", StringIO(_make_hook_input(command))), \
         patch("infrastructure.configuration.ConfigurationLoader.load", return_value=config), \
         patch("infrastructure.configuration.ConfigurationLoader.resolve_plugin_version", return_value="test"), \
         patch("infrastructure.configuration.ConfigurationLoader.resolve_log_path", return_value=Path("/tmp/test.log")), \
         patch("infrastructure.hook_output_service.HookOutputService.exit_with_success", side_effect=SystemExit(0)), \
         patch("infrastructure.git_repository.GitRepository"), \
         patch("domain.line_hasher.LineHasher"), \
         patch("services.stats_calculator.StatsCalculator"), \
         patch("services.inject_service.InjectService", return_value=mock_service):
        try:
            spec = importlib.util.spec_from_file_location(
                "ai_tracker_inject",
                HOOK_DIR / "ai-tracker-inject.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.main()
        except SystemExit:
            pass

    return mock_service


class TestInjectHookRouting:
    """Tests for command routing in ai-tracker-inject.py."""

    def test_calls_process_commit_for_git_commit(self):
        """Given a git commit command, calls process_commit()."""
        mock_service = _run_main("git commit -m 'msg'")
        mock_service.process_commit.assert_called_once()
        mock_service.recover_missed_commit.assert_not_called()

    def test_calls_process_commit_for_chained_commit(self):
        """Given git add && git commit, calls process_commit()."""
        mock_service = _run_main("git add . && git commit -m 'msg'")
        mock_service.process_commit.assert_called_once()
        mock_service.recover_missed_commit.assert_not_called()

    def test_calls_recover_for_git_push(self):
        """Given a git push command, calls recover_missed_commit()."""
        mock_service = _run_main("git push")
        mock_service.recover_missed_commit.assert_called_once()
        mock_service.process_commit.assert_not_called()

    def test_calls_recover_for_git_push_with_args(self):
        """Given git push origin main, calls recover_missed_commit()."""
        mock_service = _run_main("git push origin main")
        mock_service.recover_missed_commit.assert_called_once()
        mock_service.process_commit.assert_not_called()

    def test_skips_amend_command(self):
        """Given git commit --amend, calls neither service method."""
        mock_service = _run_main("git commit --amend --no-edit")
        mock_service.process_commit.assert_not_called()
        mock_service.recover_missed_commit.assert_not_called()

    def test_skips_unrelated_command(self):
        """Given an unrelated bash command, calls neither service method."""
        mock_service = _run_main("git status")
        mock_service.process_commit.assert_not_called()
        mock_service.recover_missed_commit.assert_not_called()

    def test_skips_git_add_command(self):
        """Given git add, calls neither service method."""
        mock_service = _run_main("git add .")
        mock_service.process_commit.assert_not_called()
        mock_service.recover_missed_commit.assert_not_called()
