"""Deletion targets detector — parses bash commands for file deletion targets."""

import re
from typing import Set

from services.bash_command_detector import _GIT_RM_PATTERN, _UNLINK_PATTERN, _RM_PATTERN


class DeletionTargetsDetector:
    """Extracts file path targets from rm, git rm, and unlink bash commands.

    Stateless — can be cached and reused across multiple commands.
    Splits multi-command strings on &&, ;, and | separators and extracts
    non-flag arguments from each deletion sub-command.
    """

    def detect(self, command: str) -> Set[str]:
        """Parse a bash command string and return raw file path tokens.

        Args:
            command: Bash command string, possibly chained with && / ; / |

        Returns:
            Set of raw path token strings (may contain globs or relative paths)
        """
        if not command:
            return set()

        targets: Set[str] = set()
        sub_commands = re.split(r'&&|;|\|', command)

        for sub in sub_commands:
            sub = sub.strip()

            # git rm [flags] <targets>
            m = _GIT_RM_PATTERN.search(sub)
            if m:
                tokens = m.group(1).split()
                targets.update(t for t in tokens if not t.startswith('-'))
                continue

            # unlink <target>  (single argument)
            m = _UNLINK_PATTERN.search(sub)
            if m:
                targets.add(m.group(1))
                continue

            # rm [flags] <targets>
            m = _RM_PATTERN.search(sub)
            if m:
                tokens = m.group(1).split()
                targets.update(t for t in tokens if not t.startswith('-'))

        return targets
