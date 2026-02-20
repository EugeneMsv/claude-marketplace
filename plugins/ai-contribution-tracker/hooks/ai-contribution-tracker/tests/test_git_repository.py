"""Tests for GitRepository HEAD methods."""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.git_repository import GitRepository


@pytest.fixture
def repo():
    return GitRepository()


class TestGetHeadCommitHash:

    def test_returns_hash_on_success(self, repo):
        """Given git rev-parse succeeds, returns the hash string."""
        mock_result = MagicMock()
        mock_result.stdout = "abc123def456abc123def456abc123def456abc12\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_head_commit_hash()

        assert result == "abc123def456abc123def456abc123def456abc12"
        mock_run.assert_called_once_with(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )

    def test_returns_none_on_subprocess_error(self, repo):
        """Given git command fails, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, 'git')
        ):
            result = repo.get_head_commit_hash()

        assert result is None

    def test_returns_none_when_git_not_found(self, repo):
        """Given git not installed, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=FileNotFoundError()
        ):
            result = repo.get_head_commit_hash()

        assert result is None

    def test_strips_trailing_newline(self, repo):
        """Given git output with newline, strips it."""
        mock_result = MagicMock()
        mock_result.stdout = "deadbeef\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_head_commit_hash()

        assert result == "deadbeef"


class TestGetHeadCommitMessage:

    def test_returns_message_on_success(self, repo):
        """Given git log succeeds, returns the commit message."""
        mock_result = MagicMock()
        mock_result.stdout = "Add feature X\n\nSome details here.\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_head_commit_message()

        assert result == "Add feature X\n\nSome details here."
        mock_run.assert_called_once_with(
            ['git', 'log', '-1', '--format=%B'],
            capture_output=True,
            text=True,
            check=True
        )

    def test_returns_none_on_subprocess_error(self, repo):
        """Given git command fails, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, 'git')
        ):
            result = repo.get_head_commit_message()

        assert result is None

    def test_returns_none_when_git_not_found(self, repo):
        """Given git not installed, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=FileNotFoundError()
        ):
            result = repo.get_head_commit_message()

        assert result is None

    def test_detects_already_injected_message(self, repo):
        """Given commit message containing AI stats, Overall: + marker is detectable."""
        mock_result = MagicMock()
        mock_result.stdout = "Fix bug\n\nOverall: +120 -30\nAI: 85%\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_head_commit_message()

        assert result is not None
        assert "Overall: +" in result


class TestAmendCommitMessage:

    @pytest.mark.parametrize("raises,expected", [
        (None, True),
        (subprocess.CalledProcessError(1, 'git'), False),
    ])
    def test_amend_returns_correct_result(self, repo, raises, expected):
        """Given git commit --amend succeeds/fails, returns True/False."""
        side_effect = raises if raises else MagicMock()
        with patch("infrastructure.git_repository.subprocess.run",
                   side_effect=raises or None,
                   return_value=MagicMock()) as mock_run:
            if raises:
                with patch("infrastructure.git_repository.subprocess.run",
                           side_effect=raises):
                    result = repo.amend_commit_message("new message")
            else:
                result = repo.amend_commit_message("new message")

        assert result == expected

    def test_amend_calls_correct_command(self, repo):
        """amend_commit_message calls git commit --amend -m with the message."""
        message = "updated commit message"
        with patch("infrastructure.git_repository.subprocess.run") as mock_run:
            repo.amend_commit_message(message)

        mock_run.assert_called_once_with(
            ['git', 'commit', '--amend', '-m', message],
            check=True,
            capture_output=True
        )

    def test_amend_returns_false_on_error(self, repo):
        """Given git amend fails, returns False without raising."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, 'git')
        ):
            result = repo.amend_commit_message("message")

        assert result is False
