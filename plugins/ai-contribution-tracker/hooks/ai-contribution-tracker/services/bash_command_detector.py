"""Bash command detection utilities for AI contribution tracker."""

import re
from enum import Enum
from typing import Callable

_COMMIT_PATTERN = re.compile(r'\bgit\s+commit\b')
_PUSH_PATTERN = re.compile(r'\bgit\s+push\b')


class DetectedCommand(Enum):
    """Enumeration of recognized bash command types."""

    GIT_COMMIT = "git_commit"
    GIT_COMMIT_AMEND = "git_commit_amend"
    GIT_PUSH = "git_push"
    UNIDENTIFIED = "unidentified"


# Each entry maps a DetectedCommand to its predicate.
# GIT_COMMIT and GIT_COMMIT_AMEND are mutually exclusive by predicate design.
# GIT_PUSH is independent and can coexist with either commit variant.
_PREDICATES: dict[DetectedCommand, Callable[[str], bool]] = {
    DetectedCommand.GIT_COMMIT: lambda cmd: bool(_COMMIT_PATTERN.search(cmd)) and '--amend' not in cmd,
    DetectedCommand.GIT_COMMIT_AMEND: lambda cmd: bool(_COMMIT_PATTERN.search(cmd)) and '--amend' in cmd,
    DetectedCommand.GIT_PUSH: lambda cmd: bool(_PUSH_PATTERN.search(cmd)),
}


class BashCommandDetector:
    """Detects git command patterns in bash command strings.

    Centralizes command pattern detection used across hooks and services.
    """

    @staticmethod
    def detect_commands(command: str) -> set[DetectedCommand]:
        """Return the set of commands detected in the given bash command string.

        GIT_COMMIT and GIT_COMMIT_AMEND are mutually exclusive.
        GIT_PUSH may appear alongside either.
        Returns {UNIDENTIFIED} when no known command is detected or input is empty.

        Args:
            command: Bash command string to inspect

        Returns:
            Set of DetectedCommand values matching the command
        """
        if not command:
            return {DetectedCommand.UNIDENTIFIED}
        result = {cmd for cmd, predicate in _PREDICATES.items() if predicate(command)}
        return result or {DetectedCommand.UNIDENTIFIED}
