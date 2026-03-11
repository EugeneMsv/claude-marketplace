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


class TestGetRemoteUrl:

    def test_returns_url_on_success(self, repo):
        """Given git remote get-url succeeds, returns the URL string."""
        mock_result = MagicMock()
        mock_result.stdout = "git@github.com:alice/my-repo.git\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_remote_url()

        assert result == "git@github.com:alice/my-repo.git"
        mock_run.assert_called_once_with(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True,
            text=True,
            check=True
        )

    def test_returns_none_on_subprocess_error(self, repo):
        """Given no remote configured, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(2, 'git')
        ):
            result = repo.get_remote_url()

        assert result is None

    def test_returns_none_on_empty_output(self, repo):
        """Given empty stdout, returns None."""
        mock_result = MagicMock()
        mock_result.stdout = "   \n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_remote_url()

        assert result is None

    def test_returns_none_when_git_not_found(self, repo):
        """Given git not installed, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=FileNotFoundError()
        ):
            result = repo.get_remote_url()

        assert result is None


class TestGetHeadCommitTimestamp:

    def test_returns_iso_timestamp_on_success(self, repo):
        """Given git log succeeds, returns ISO 8601 timestamp."""
        mock_result = MagicMock()
        mock_result.stdout = "2026-02-10T14:22:00+00:00\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_head_commit_timestamp()

        assert result == "2026-02-10T14:22:00+00:00"
        mock_run.assert_called_once_with(
            ['git', 'log', '-1', '--format=%aI', 'HEAD'],
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
            result = repo.get_head_commit_timestamp()

        assert result is None

    def test_returns_none_on_empty_output(self, repo):
        """Given empty stdout, returns None."""
        mock_result = MagicMock()
        mock_result.stdout = "\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_head_commit_timestamp()

        assert result is None


class TestGetHeadCommitSubject:

    def test_returns_subject_on_success(self, repo):
        """Given git log succeeds, returns the first-line subject."""
        mock_result = MagicMock()
        mock_result.stdout = "Task 3: implement payment retry logic\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_head_commit_subject()

        assert result == "Task 3: implement payment retry logic"
        mock_run.assert_called_once_with(
            ['git', 'log', '-1', '--format=%s', 'HEAD'],
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
            result = repo.get_head_commit_subject()

        assert result is None

    def test_returns_none_on_empty_output(self, repo):
        """Given empty commit subject, returns None."""
        mock_result = MagicMock()
        mock_result.stdout = "\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_head_commit_subject()

        assert result is None


class TestGetAuthorEmail:

    def test_returns_email_on_success(self, repo):
        """Given git config succeeds, returns the email string."""
        mock_result = MagicMock()
        mock_result.stdout = "alice@example.com\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_author_email()

        assert result == "alice@example.com"
        mock_run.assert_called_once_with(
            ['git', 'config', 'user.email'],
            capture_output=True,
            text=True,
            check=True
        )

    def test_returns_none_when_not_configured(self, repo):
        """Given git config not set, returns None."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, 'git')
        ):
            result = repo.get_author_email()

        assert result is None

    def test_returns_none_on_empty_output(self, repo):
        """Given empty email output, returns None."""
        mock_result = MagicMock()
        mock_result.stdout = "  \n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_author_email()

        assert result is None


class TestGetChangedFileCount:

    def test_returns_count_on_success(self, repo):
        """Given git diff returns file names, returns correct count."""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py\nsrc/utils.py\ntests/test_main.py\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result) as mock_run:
            result = repo.get_changed_file_count("abc123")

        assert result == 3
        mock_run.assert_called_once_with(
            ['git', 'diff', '--name-only', 'abc123', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )

    def test_returns_zero_on_empty_diff(self, repo):
        """Given no changed files, returns 0."""
        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_changed_file_count("abc123")

        assert result == 0

    def test_returns_zero_on_subprocess_error(self, repo):
        """Given git command fails, returns 0."""
        with patch(
            "infrastructure.git_repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, 'git')
        ):
            result = repo.get_changed_file_count("abc123")

        assert result == 0

    def test_ignores_blank_lines_in_output(self, repo):
        """Given diff output with blank lines, counts only non-empty lines."""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.py\n\nsrc/utils.py\n\n"

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_changed_file_count("abc123")

        assert result == 2

    @pytest.mark.parametrize("file_list,expected_count", [
        ("file1.py\n", 1),
        ("file1.py\nfile2.py\nfile3.py\n", 3),
        ("\n\n\n", 0),
    ])
    def test_counts_various_file_counts(self, repo, file_list, expected_count):
        """Given various diff outputs, returns correct file count."""
        mock_result = MagicMock()
        mock_result.stdout = file_list

        with patch("infrastructure.git_repository.subprocess.run", return_value=mock_result):
            result = repo.get_changed_file_count("deadbeef")

        assert result == expected_count
