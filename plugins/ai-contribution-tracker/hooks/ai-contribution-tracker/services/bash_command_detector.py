"""Bash command detection utilities for AI contribution tracker."""

import re


class BashCommandDetector:
    """Detects git command patterns in bash command strings.

    Centralizes command pattern detection used across hooks and services.
    """

    COMMIT_PATTERN = re.compile(r'\bgit\s+commit\b')
    PUSH_PATTERN = re.compile(r'\bgit\s+push\b')

    @staticmethod
    def is_git_commit(command: str) -> bool:
        """Return True if command contains a git commit invocation.

        Args:
            command: Bash command string to inspect

        Returns:
            True if the command invokes git commit
        """
        return bool(command and BashCommandDetector.COMMIT_PATTERN.search(command))

    @staticmethod
    def is_git_commit_amend(command: str) -> bool:
        """Return True if command is a git commit --amend.

        Args:
            command: Bash command string to inspect

        Returns:
            True if the command contains --amend flag
        """
        return '--amend' in command

    @staticmethod
    def is_git_push(command: str) -> bool:
        """Return True if command contains a git push invocation.

        Args:
            command: Bash command string to inspect

        Returns:
            True if the command invokes git push
        """
        return bool(command and BashCommandDetector.PUSH_PATTERN.search(command))
