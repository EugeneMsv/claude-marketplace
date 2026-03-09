"""Ignored files detection domain object."""

import fnmatch
from pathlib import Path
from typing import Dict, Set, Union


class IgnoredFilesDetector:
    """Detects whether a file path matches ignored-files glob patterns.

    Uses Python's fnmatch for matching. Since fnmatch treats '*' as matching
    any character including '/', patterns like '**/generated/**' correctly match
    paths at any depth. A **/ fallback is pre-built at construction time to handle
    paths with no leading directory component (e.g. 'generated/Foo.java' at repo root).
    """

    def __init__(self, patterns: Set[str]):
        """Initialize with a set of Ant-style glob patterns.

        Args:
            patterns: Glob patterns to match against file paths (e.g. '**/generated/**')
        """
        self._patterns = set(patterns)
        # Pre-build fallback patterns — strip leading '**/' for root-level paths.
        # Avoids slicing on every is_ignored() call.
        self._fallbacks: Dict[str, str] = {
            p: p[3:] for p in self._patterns if p.startswith('**/')
        }

    def is_ignored(self, path: Union[str, Path]) -> bool:
        """Return True on the first pattern match (short-circuit).

        Args:
            path: File path to check (absolute or relative, any OS separator)

        Returns:
            True if path matches any configured pattern
        """
        if not self._patterns:
            return False
        normalized = str(path).replace('\\', '/')
        for pattern in self._patterns:
            if fnmatch.fnmatch(normalized, pattern):
                return True
            fallback = self._fallbacks.get(pattern)
            if fallback and fnmatch.fnmatch(normalized, fallback):
                return True
        return False

    def matched_patterns(self, path: Union[str, Path]) -> Set[str]:
        """Return all patterns that matched the given path.

        Performs a full scan (no short-circuit). Used by StatsCalculator to
        record which patterns contributed to the ignored-files bucket.

        Args:
            path: File path to check

        Returns:
            Set of matched pattern strings (empty if none matched)
        """
        if not self._patterns:
            return set()
        normalized = str(path).replace('\\', '/')
        matched: Set[str] = set()
        for pattern in self._patterns:
            if fnmatch.fnmatch(normalized, pattern):
                matched.add(pattern)
            else:
                fallback = self._fallbacks.get(pattern)
                if fallback and fnmatch.fnmatch(normalized, fallback):
                    matched.add(pattern)
        return matched
