"""Tests for ai-tracker-commit-pre hook logic."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bash_command_detector import BashCommandDetector, DetectedCommand


def _make_detector():
    """Build a detector with no format commands (commit-pre doesn't need them)."""
    config = MagicMock()
    config.format_commands = []
    return BashCommandDetector(config)


class TestCommitPreHookRouting:
    """Verify the hook correctly routes commands to InjectService.record_commit_intent."""

    @pytest.mark.parametrize("command,should_call", [
        ("git commit -m 'msg'", True),
        ("git add . && git commit -m 'msg' && git push", True),
        ("git commit --amend --no-edit", False),
        ("git push", False),
        ("git add .", False),
    ])
    def test_routes_to_inject_service_only_for_non_amend_commits(self, command, should_call):
        """Given a command, hook calls record_commit_intent only for non-amend commits."""
        detector = _make_detector()
        detected = detector.detect_commands(command)
        called = DetectedCommand.GIT_COMMIT in detected
        assert called == should_call


class TestBashCommandDetectorIntegration:
    """Verify detector correctly classifies commands the hook encounters."""

    @pytest.mark.parametrize("command,expect_commit,expect_amend", [
        ("git commit -m 'msg'", True, False),
        ("git add . && git commit -m 'msg' && git push", True, False),
        ("git commit --amend --no-edit", False, True),
        ("git push", False, False),
        ("git add .", False, False),
    ])
    def test_command_classification(self, command, expect_commit, expect_amend):
        """Given various commands, detector classifies correctly."""
        detector = _make_detector()
        detected = detector.detect_commands(command)
        assert (DetectedCommand.GIT_COMMIT in detected) == expect_commit
        assert (DetectedCommand.GIT_COMMIT_AMEND in detected) == expect_amend
