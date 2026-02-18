"""Tests for GlabRepository."""

import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.glab_repository import GlabRepository


@pytest.fixture
def logger():
    return logging.getLogger("test")


@pytest.fixture
def glab(logger):
    return GlabRepository(logger)


class TestIsAvailable:

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_true_when_glab_installed(self, mock_run, glab):
        """Given glab is installed, is_available returns True."""
        mock_run.return_value = MagicMock(returncode=0)
        assert glab.is_available() is True

    @patch("infrastructure.glab_repository.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_glab_missing(self, mock_run, glab):
        """Given glab not installed, is_available returns False."""
        assert glab.is_available() is False

    @patch("infrastructure.glab_repository.subprocess.run", side_effect=subprocess.TimeoutExpired("glab", 5))
    def test_returns_false_on_timeout(self, mock_run, glab):
        """Given glab times out, is_available returns False."""
        assert glab.is_available() is False


class TestGetMrForBranch:

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_mr_when_found(self, mock_run, glab):
        """Given MR exists for branch, returns dict with iid, title, and description."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([{"iid": 42, "title": "My MR", "description": "My description"}]),
            returncode=0
        )
        result = glab.get_mr_for_branch("feature/test")
        assert result == {"iid": "42", "title": "My MR", "description": "My description"}

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_empty_description_when_missing(self, mock_run, glab):
        """Given MR without description field, returns empty string."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([{"iid": 42, "title": "My MR"}]),
            returncode=0
        )
        result = glab.get_mr_for_branch("feature/test")
        assert result["description"] == ""

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_none_when_no_mr(self, mock_run, glab):
        """Given no MR for branch, returns None."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        assert glab.get_mr_for_branch("feature/orphan") is None

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_first_when_multiple_mrs(self, mock_run, glab):
        """Given multiple MRs, returns first one."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([
                {"iid": 10, "title": "First"},
                {"iid": 20, "title": "Second"}
            ]),
            returncode=0
        )
        result = glab.get_mr_for_branch("feature/multi")
        assert result["iid"] == "10"

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.CalledProcessError(1, "glab"))
    def test_returns_none_on_command_failure(self, mock_run, glab):
        """Given glab command fails, returns None."""
        assert glab.get_mr_for_branch("feature/fail") is None

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.TimeoutExpired("glab", 10))
    def test_returns_none_on_timeout(self, mock_run, glab):
        """Given glab times out, returns None."""
        assert glab.get_mr_for_branch("feature/slow") is None

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_none_on_invalid_json(self, mock_run, glab):
        """Given malformed JSON output, returns None."""
        mock_run.return_value = MagicMock(stdout="not json", returncode=0)
        assert glab.get_mr_for_branch("feature/bad") is None


class TestUpdateMrTitle:

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_true_on_success(self, mock_run, glab):
        """Given successful update, returns True."""
        mock_run.return_value = MagicMock(returncode=0)
        assert glab.update_mr_title("42", "New Title [AI: 85%]") is True

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.CalledProcessError(1, "glab"))
    def test_returns_false_on_failure(self, mock_run, glab):
        """Given update fails, returns False."""
        assert glab.update_mr_title("42", "Title") is False

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.TimeoutExpired("glab", 10))
    def test_returns_false_on_timeout(self, mock_run, glab):
        """Given update times out, returns False."""
        assert glab.update_mr_title("42", "Title") is False


class TestUpdateMrDescription:

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_true_on_success(self, mock_run, glab):
        """Given successful update, returns True."""
        mock_run.return_value = MagicMock(returncode=0)
        assert glab.update_mr_description("42", "New description with stats") is True

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.CalledProcessError(1, "glab"))
    def test_returns_false_on_failure(self, mock_run, glab):
        """Given update fails, returns False."""
        assert glab.update_mr_description("42", "Description") is False

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.TimeoutExpired("glab", 10))
    def test_returns_false_on_timeout(self, mock_run, glab):
        """Given update times out, returns False."""
        assert glab.update_mr_description("42", "Description") is False


class TestCreateDraftMr:

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_true_on_success(self, mock_run, glab):
        """Given successful creation, returns True."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = glab.create_draft_mr("feature/test", "PROJ-123 Test feature", "main")
        assert result is True
        mock_run.assert_called_once_with(
            [
                'glab', 'mr', 'create',
                '--draft',
                '--title', 'PROJ-123 Test feature',
                '--source-branch', 'feature/test',
                '--target-branch', 'main',
                '--description', '',
                '--yes'
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_includes_description_when_provided(self, mock_run, glab):
        """Given description parameter, includes it in MR creation."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        description = "## AI Contribution Stats\n\n```\nStats here\n```"
        result = glab.create_draft_mr("feature/test", "Title", "main", description)
        assert result is True
        # Verify description was passed
        call_args = mock_run.call_args[0][0]
        assert '--description' in call_args
        desc_index = call_args.index('--description')
        assert call_args[desc_index + 1] == description

    @patch("infrastructure.glab_repository.subprocess.run")
    def test_returns_false_on_failure(self, mock_run, glab):
        """Given creation fails, returns False."""
        error = subprocess.CalledProcessError(1, "glab")
        error.stderr = "error message"
        error.stdout = "output message"
        mock_run.side_effect = error
        assert glab.create_draft_mr("feature/test", "Title", "main") is False

    @patch("infrastructure.glab_repository.subprocess.run",
           side_effect=subprocess.TimeoutExpired("glab", 10))
    def test_returns_false_on_timeout(self, mock_run, glab):
        """Given creation times out, returns False."""
        assert glab.create_draft_mr("feature/test", "Title", "main") is False
