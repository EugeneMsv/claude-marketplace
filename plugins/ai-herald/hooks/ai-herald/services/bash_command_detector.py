"""Bash command detection utilities for AI contribution tracker."""

import re
from enum import Enum
from typing import Callable, List

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
_MERGE_PATTERN  = re.compile(rf'\bgit{_GIT_GLOBAL_FLAGS}\s+merge\b')
_REBASE_PATTERN = re.compile(rf'\bgit{_GIT_GLOBAL_FLAGS}\s+rebase\b')

# Patterns for file deletion commands.
# Captures targets after optional flag tokens (tokens starting with '-').
_RM_PATTERN      = re.compile(r'\brm\b((?:\s+(?:-\S+|\S+))*)')
_GIT_RM_PATTERN  = re.compile(rf'\bgit{_GIT_GLOBAL_FLAGS}\s+rm\b((?:\s+(?:-\S+|\S+))*)')
_UNLINK_PATTERN  = re.compile(r'\bunlink\b\s+(\S+)')

# Grouped for boolean detection (gate check only — extraction uses patterns individually).
_DELETION_PATTERNS = [_GIT_RM_PATTERN, _UNLINK_PATTERN, _RM_PATTERN]


class DetectedCommand(Enum):
    """Enumeration of recognized bash command types."""

    GIT_COMMIT = "git_commit"
    GIT_COMMIT_AMEND = "git_commit_amend"
    GIT_PUSH = "git_push"
    GIT_PUSH_TAGS = "git_push_tags"
    GIT_MERGE = "git_merge"
    GIT_REBASE = "git_rebase"
    CODE_FORMATTER = "code_formatter"
    BASH_FILE_DELETION = "bash_file_deletion"
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
            DetectedCommand.GIT_MERGE: lambda cmd: bool(_MERGE_PATTERN.search(cmd)),
            DetectedCommand.GIT_REBASE: lambda cmd: bool(_REBASE_PATTERN.search(cmd)),
            DetectedCommand.CODE_FORMATTER: formatter_predicate,
            DetectedCommand.BASH_FILE_DELETION: lambda cmd: any(p.search(cmd) for p in _DELETION_PATTERNS),
        }

        # Patterns used by detect_commands_ordered to locate match positions.
        # Order must parallel the keys of self._predicates that have git subcommand tokens.
        self._ordered_patterns: List[tuple[DetectedCommand, re.Pattern]] = [
            (DetectedCommand.GIT_COMMIT, _COMMIT_PATTERN),
            (DetectedCommand.GIT_COMMIT_AMEND, _COMMIT_PATTERN),
            (DetectedCommand.GIT_PUSH_TAGS, _PUSH_PATTERN),
            (DetectedCommand.GIT_PUSH, _PUSH_PATTERN),
            (DetectedCommand.GIT_MERGE, _MERGE_PATTERN),
            (DetectedCommand.GIT_REBASE, _REBASE_PATTERN),
        ]

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

    def detect_commands_ordered(self, command: str) -> List[DetectedCommand]:
        """Return detected commands sorted by their first match position in the command string.

        Used by the inject hook to execute handlers in the correct sequence for
        chained commands (e.g. ``git merge origin/main && git commit -m "fix"``
        produces [GIT_MERGE, GIT_COMMIT]).

        Only git subcommand-bearing entries are position-ordered (commit, push,
        merge, rebase). CODE_FORMATTER and BASH_FILE_DELETION are not included.
        Returns empty list when no positional command is detected or input is empty.

        Args:
            command: Bash command string to inspect

        Returns:
            List of detected DetectedCommand values ordered by match position
        """
        if not command:
            return []

        # Collect (position, DetectedCommand) for each matching command.
        # Predicate guards are re-evaluated here to respect mutual-exclusion rules.
        entries: List[tuple[int, DetectedCommand]] = []
        seen_patterns: dict[re.Pattern, int] = {}  # pattern → earliest match position

        for detected_cmd, pattern in self._ordered_patterns:
            predicate = self._predicates.get(detected_cmd)
            if predicate is None or not predicate(command):
                continue
            if pattern not in seen_patterns:
                m = pattern.search(command)
                if m:
                    seen_patterns[pattern] = m.start()
            pos = seen_patterns.get(pattern)
            if pos is not None:
                entries.append((pos, detected_cmd))

        entries.sort(key=lambda x: x[0])
        return [cmd for _, cmd in entries]
