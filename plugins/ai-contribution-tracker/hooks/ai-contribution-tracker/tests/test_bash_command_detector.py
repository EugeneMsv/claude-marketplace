"""Tests for BashCommandDetector."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bash_command_detector import BashCommandDetector


class TestIsGitCommit:

    @pytest.mark.parametrize("command", [
        "git commit -m 'msg'",
        "git add . && git commit -m 'msg'",
        "git commit -m 'msg' && git push",
        "git  commit -m 'msg'",  # extra whitespace
        "git commit --amend",   # amend is still a commit
    ])
    def test_returns_true_for_commit_commands(self, command):
        """Given a command containing git commit, returns True."""
        assert BashCommandDetector.is_git_commit(command) is True

    @pytest.mark.parametrize("command", [
        "git push",
        "git add .",
        "git status",
        "echo commit something",
        "",
        None,
    ])
    def test_returns_false_for_non_commit_commands(self, command):
        """Given a command without git commit (or empty/None), returns False."""
        assert BashCommandDetector.is_git_commit(command) is False


class TestIsGitCommitAmend:

    @pytest.mark.parametrize("command", [
        "git commit --amend",
        "git commit --amend -m 'msg'",
        "git commit --amend --no-edit",
    ])
    def test_returns_true_for_amend_commands(self, command):
        """Given a command with --amend flag, returns True."""
        assert BashCommandDetector.is_git_commit_amend(command) is True

    @pytest.mark.parametrize("command", [
        "git commit -m 'msg'",
        "git push",
        "git add . && git commit -m 'fix'",
        "",
    ])
    def test_returns_false_for_non_amend_commands(self, command):
        """Given a command without --amend, returns False."""
        assert BashCommandDetector.is_git_commit_amend(command) is False


class TestIsGitPush:

    @pytest.mark.parametrize("command", [
        "git push",
        "git push origin main",
        "git push --set-upstream origin feature",
        "git add . && git commit -m 'msg' && git push",
        "git  push origin",  # extra whitespace
    ])
    def test_returns_true_for_push_commands(self, command):
        """Given a command containing git push, returns True."""
        assert BashCommandDetector.is_git_push(command) is True

    @pytest.mark.parametrize("command", [
        "git commit -m 'msg'",
        "git add .",
        "git status",
        "echo push something",
        "",
        None,
    ])
    def test_returns_false_for_non_push_commands(self, command):
        """Given a command without git push (or empty/None), returns False."""
        assert BashCommandDetector.is_git_push(command) is False
