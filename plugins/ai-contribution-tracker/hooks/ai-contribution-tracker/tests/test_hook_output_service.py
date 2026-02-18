"""Tests for hook output service."""

import json
import sys
import pytest
from io import StringIO
from unittest.mock import patch

from infrastructure.hook_output_service import HookOutputService


class TestExitWithSuccess:
    """Tests for exit_with_success method."""

    def test_outputs_json_and_exits_with_code_0(self):
        """Given message, outputs JSON with prefixed message and exits 0."""
        service = HookOutputService("1.0.0")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit) as exc_info:
                service.exit_with_success("Test success message")

        assert exc_info.value.code == 0
        data = json.loads(mock_stdout.getvalue())
        assert data["systemMessage"] == "[ai-tracker:1.0.0] Test success message"

    def test_without_message_exits_cleanly(self):
        """Given no message, exits with code 0 and no output."""
        service = HookOutputService()

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit) as exc_info:
                service.exit_with_success()

        assert exc_info.value.code == 0
        assert mock_stdout.getvalue() == ""


class TestExitWithFailure:
    """Tests for exit_with_failure method."""

    def test_outputs_json_and_exits_with_code_1(self):
        """Given message, outputs JSON with prefixed message and exits 1."""
        service = HookOutputService("2.0.0")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit) as exc_info:
                service.exit_with_failure("Test failure message")

        assert exc_info.value.code == 1
        data = json.loads(mock_stdout.getvalue())
        assert data["systemMessage"] == "[ai-tracker:2.0.0] Test failure message"

    def test_without_message_exits_cleanly(self):
        """Given no message, exits with code 1 and no output."""
        service = HookOutputService()

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit) as exc_info:
                service.exit_with_failure()

        assert exc_info.value.code == 1
        assert mock_stdout.getvalue() == ""


class TestVersionPrefix:
    """Tests for version-based prefix."""

    def test_prefix_includes_version(self):
        """Given version, prefix contains version string."""
        service = HookOutputService("0.0.14")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit):
                service.exit_with_success("msg")

        data = json.loads(mock_stdout.getvalue())
        assert data["systemMessage"].startswith("[ai-tracker:0.0.14]")

    def test_default_version_is_dev(self):
        """Given no version arg, prefix uses 'dev'."""
        service = HookOutputService()

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit):
                service.exit_with_success("msg")

        data = json.loads(mock_stdout.getvalue())
        assert data["systemMessage"].startswith("[ai-tracker:dev]")

    def test_json_format_is_valid(self):
        """Given message, output is valid JSON with correct structure."""
        service = HookOutputService("1.0.0")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with pytest.raises(SystemExit):
                service.exit_with_success("Valid JSON test")

        data = json.loads(mock_stdout.getvalue())
        assert isinstance(data, dict)
        assert "systemMessage" in data
        assert isinstance(data["systemMessage"], str)
