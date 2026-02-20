"""Tests for BashCommandDetector.detect_commands."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bash_command_detector import BashCommandDetector, DetectedCommand


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
        # Push only
        ("git push",                                    {DetectedCommand.GIT_PUSH}),
        ("git push origin main",                        {DetectedCommand.GIT_PUSH}),
        ("git push --set-upstream origin feature",      {DetectedCommand.GIT_PUSH}),
        ("git  push origin",                            {DetectedCommand.GIT_PUSH}),  # extra whitespace
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
        assert BashCommandDetector.detect_commands(command) == expected

    def test_git_commit_and_git_commit_amend_are_mutually_exclusive(self):
        """GIT_COMMIT and GIT_COMMIT_AMEND never appear in the same result set."""
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
            result = BashCommandDetector.detect_commands(cmd)
            assert not (DetectedCommand.GIT_COMMIT in result and DetectedCommand.GIT_COMMIT_AMEND in result), (
                f"Both GIT_COMMIT and GIT_COMMIT_AMEND found for: {cmd!r}"
            )
