"""Bash command detection utilities for AI contribution tracker."""

import re
from enum import Enum
from typing import Callable

# Matches a single git global option that can appear before the subcommand:
#   --long-flag or --long-flag=value  (e.g. --no-pager, --git-dir=/path)
#   -C /path or -c key=val            (short flags that always take a value)
#   -X                                (short boolean flag, e.g. -p, -P)
# Subcommands (commit, push, …) never start with '-', so this pattern
# safely stops before consuming them.
_GIT_GLOBAL_OPT = r'(?:--[\w][\w-]*(?:=\S+)?|-[Cc]\s+\S+|-[a-zA-Z])'
_GIT_GLOBAL_FLAGS = rf'(?:\s+{_GIT_GLOBAL_OPT})*'
_COMMIT_PATTERN = re.compile(rf'\bgit{_GIT_GLOBAL_FLAGS}\s+commit\b')
_PUSH_PATTERN   = re.compile(rf'\bgit{_GIT_GLOBAL_FLAGS}\s+push\b')


class DetectedCommand(Enum):
    """Enumeration of recognized bash command types."""

    GIT_COMMIT = "git_commit"
    GIT_COMMIT_AMEND = "git_commit_amend"
    GIT_PUSH = "git_push"
    GIT_PUSH_TAGS = "git_push_tags"
    CODE_FORMATTER = "code_formatter"
    UNIDENTIFIED = "unidentified"


class BashCommandDetector:
    """Detects git command patterns in bash command strings.

    Instance-based; constructor receives config so that CODE_FORMATTER
    predicate is built from the configured formatter list.
    """

    def __init__(self, config):
        """Initialize detector with configuration.

        Args:
            config: Configuration object with format_commands list
        """
        format_commands = config.format_commands or []
        if format_commands:
            patterns = [rf'\b{re.escape(cmd)}\b' for cmd in format_commands]
            formatter_pattern = re.compile('|'.join(patterns))
            formatter_predicate: Callable[[str], bool] = lambda cmd, p=formatter_pattern: bool(p.search(cmd))
        else:
            formatter_predicate = lambda cmd: False

        # Each entry maps a DetectedCommand to its predicate.
        # GIT_COMMIT and GIT_COMMIT_AMEND are mutually exclusive by predicate design.
        # GIT_PUSH and GIT_PUSH_TAGS are mutually exclusive by predicate design.
        self._predicates: dict[DetectedCommand, Callable[[str], bool]] = {
            DetectedCommand.GIT_COMMIT: lambda cmd: bool(_COMMIT_PATTERN.search(cmd)) and '--amend' not in cmd,
            DetectedCommand.GIT_COMMIT_AMEND: lambda cmd: bool(_COMMIT_PATTERN.search(cmd)) and '--amend' in cmd,
            DetectedCommand.GIT_PUSH_TAGS: lambda cmd: bool(_PUSH_PATTERN.search(cmd)) and ('--tags' in cmd or 'refs/tags/' in cmd),
            DetectedCommand.GIT_PUSH: lambda cmd: bool(_PUSH_PATTERN.search(cmd)) and '--tags' not in cmd and 'refs/tags/' not in cmd,
            DetectedCommand.CODE_FORMATTER: formatter_predicate,
        }

    def detect_commands(self, command: str) -> set[DetectedCommand]:
        """Return the set of commands detected in the given bash command string.

        GIT_COMMIT and GIT_COMMIT_AMEND are mutually exclusive.
        GIT_PUSH and GIT_PUSH_TAGS are mutually exclusive.
        CODE_FORMATTER only matches when format_commands is non-empty.
        Returns {UNIDENTIFIED} when no known command is detected or input is empty.

        Args:
            command: Bash command string to inspect

        Returns:
            Set of DetectedCommand values matching the command
        """
        if not command:
            return {DetectedCommand.UNIDENTIFIED}
        result = {cmd for cmd, predicate in self._predicates.items() if predicate(command)}
        return result or {DetectedCommand.UNIDENTIFIED}
