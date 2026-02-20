"""Tests for BashCommandDetector.detect_commands."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bash_command_detector import BashCommandDetector, DetectedCommand


def _make_detector(format_commands=None):
    """Build a BashCommandDetector with a config mock."""
    config = MagicMock()
    config.format_commands = format_commands or []
    return BashCommandDetector(config)


class TestDetectCommands:

    @pytest.mark.parametrize("command, expected", [
        # Plain commits
        ("git commit -m 'msg'",                         {DetectedCommand.GIT_COMMIT}),
        ("git add . && git commit -m 'msg'",            {DetectedCommand.GIT_COMMIT}),
        ("git  commit -m 'msg'",                        {DetectedCommand.GIT_COMMIT}),  # extra whitespace
        # Amend commits
        ("git commit --amend",                          {DetectedCommand.GIT_COMMIT_AMEND}),
        ("git commit --amend -m 'msg'",                 {DetectedCommand.GIT_COMMIT_AMEND}),
        ("git commit --amend --no-edit",                {DetectedCommand.GIT_COMMIT_AMEND}),
        # Push only (no tags)
        ("git push",                                    {DetectedCommand.GIT_PUSH}),
        ("git push origin main",                        {DetectedCommand.GIT_PUSH}),
        ("git push --set-upstream origin feature",      {DetectedCommand.GIT_PUSH}),
        ("git  push origin",                            {DetectedCommand.GIT_PUSH}),  # extra whitespace
        # Push tags (mutually exclusive with GIT_PUSH)
        ("git push --tags",                             {DetectedCommand.GIT_PUSH_TAGS}),
        ("git push origin --tags",                      {DetectedCommand.GIT_PUSH_TAGS}),
        ("git push origin refs/tags/v1.0",              {DetectedCommand.GIT_PUSH_TAGS}),
        # Commit + push (chained)
        ("git commit -m 'msg' && git push",             {DetectedCommand.GIT_COMMIT, DetectedCommand.GIT_PUSH}),
        ("git add . && git commit -m 'fix' && git push", {DetectedCommand.GIT_COMMIT, DetectedCommand.GIT_PUSH}),
        # Amend + push (chained)
        ("git commit --amend && git push",              {DetectedCommand.GIT_COMMIT_AMEND, DetectedCommand.GIT_PUSH}),
        ("git commit --amend --no-edit && git push",    {DetectedCommand.GIT_COMMIT_AMEND, DetectedCommand.GIT_PUSH}),
        # Unidentified
        ("git status",                                  {DetectedCommand.UNIDENTIFIED}),
        ("git add .",                                   {DetectedCommand.UNIDENTIFIED}),
        ("echo commit something",                       {DetectedCommand.UNIDENTIFIED}),
        ("echo push something",                         {DetectedCommand.UNIDENTIFIED}),
        ("",                                            {DetectedCommand.UNIDENTIFIED}),
        (None,                                          {DetectedCommand.UNIDENTIFIED}),
    ])
    def test_detect_commands(self, command, expected):
        """Given a bash command string, detect_commands returns the correct set of DetectedCommand values."""
        detector = _make_detector()
        assert detector.detect_commands(command) == expected

    def test_git_commit_and_git_commit_amend_are_mutually_exclusive(self):
        """GIT_COMMIT and GIT_COMMIT_AMEND never appear in the same result set."""
        detector = _make_detector()
        commands = [
            "git commit -m 'msg'",
            "git commit --amend",
            "git commit --amend && git push",
            "git commit -m 'msg' && git push",
            "git push",
            "",
            None,
        ]
        for cmd in commands:
            result = detector.detect_commands(cmd)
            assert not (DetectedCommand.GIT_COMMIT in result and DetectedCommand.GIT_COMMIT_AMEND in result), (
                f"Both GIT_COMMIT and GIT_COMMIT_AMEND found for: {cmd!r}"
            )

    def test_git_push_and_git_push_tags_are_mutually_exclusive(self):
        """GIT_PUSH and GIT_PUSH_TAGS never appear in the same result set."""
        detector = _make_detector()
        commands = [
            "git push",
            "git push origin main",
            "git push --tags",
            "git push origin refs/tags/v1.0",
            "git commit -m 'msg' && git push",
            "",
            None,
        ]
        for cmd in commands:
            result = detector.detect_commands(cmd)
            assert not (DetectedCommand.GIT_PUSH in result and DetectedCommand.GIT_PUSH_TAGS in result), (
                f"Both GIT_PUSH and GIT_PUSH_TAGS found for: {cmd!r}"
            )


class TestCodeFormatterDetection:

    @pytest.mark.parametrize("command, format_commands, should_match", [
        # Matches configured formatter
        ("./gradlew spotlessApply", ["spotlessApply"], True),
        ("prettier --write src/", ["prettier"], True),
        ("black .", ["black"], True),
        # Chained with git
        ("./gradlew spotlessApply && git add . && git commit -m 'fmt'", ["spotlessApply"], True),
        # Does not match unconfigured formatter
        ("black .", ["spotlessApply"], False),
        ("prettier src/", ["black"], False),
        # No format_commands configured → never matches
        ("spotlessApply", [], False),
        ("black .", [], False),
        # Word boundary prevents partial matches
        ("grep better_spotlessApply file.txt", ["spotlessApply"], False),
    ])
    def test_code_formatter_detection(self, command, format_commands, should_match):
        """Given a command and configured formatters, CODE_FORMATTER is detected correctly."""
        detector = _make_detector(format_commands)
        result = detector.detect_commands(command)
        assert (DetectedCommand.CODE_FORMATTER in result) == should_match

    def test_formatter_combined_with_commit(self):
        """Formatter command detected alongside git commit in chained command."""
        detector = _make_detector(["spotlessApply"])
        result = detector.detect_commands("./gradlew spotlessApply && git add . && git commit -m 'fmt'")
        assert DetectedCommand.CODE_FORMATTER in result
        assert DetectedCommand.GIT_COMMIT in result

    def test_no_format_commands_never_returns_code_formatter(self):
        """When format_commands is empty, CODE_FORMATTER is never in result."""
        detector = _make_detector([])
        for cmd in ["spotlessApply", "prettier src/", "black .", "git push"]:
            result = detector.detect_commands(cmd)
            assert DetectedCommand.CODE_FORMATTER not in result, f"Unexpected CODE_FORMATTER for: {cmd!r}"
