"""
Token-based normalization for code format equivalence checking.

This module provides token extraction and comparison for detecting when code
has been reformatted but remains semantically identical. It handles cases like:
- One line split into multiple lines
- Multiple lines joined into one line
- Whitespace and indentation changes
"""

import re
from typing import List, Set


class TokenNormalizer:
    """
    Provides token extraction and comparison for format-equivalence checking.
    Handles multi-line reformatting scenarios where line count changes.
    """

    def __init__(self):
        # Regex pattern to extract tokens (words, identifiers, operators, punctuation)
        # Splits on whitespace and extracts meaningful tokens
        # Matches: identifiers, numbers, operators, punctuation
        self._token_pattern = re.compile(r'\w+|[^\w\s]')

    def extract_tokens(self, text: str) -> List[str]:
        """
        Extract meaningful tokens from code, removing all whitespace.

        Args:
            text: Code text (can be single line or multi-line)

        Returns:
            List of tokens in order they appear

        Example:
            >>> normalizer = TokenNormalizer()
            >>> normalizer.extract_tokens("result = calculate(  x,  y  )")
            ['result', '=', 'calculate(', 'x,', 'y', ')']
        """
        if not text or not text.strip():
            return []

        # Find all non-whitespace tokens
        tokens = self._token_pattern.findall(text)
        return tokens

    def calculate_token_overlap(self, tokens1: List[str], tokens2: List[str]) -> float:
        """
        Calculate containment ratio of tokens1 within tokens2.

        Containment ratio = |intersection| / |tokens1|

        Answers: "are all AI snapshot tokens still present in the file?"
        This is independent of file size, unlike Jaccard similarity, which
        would be diluted by a large file denominator regardless of whether
        all AI tokens are present.

        Args:
            tokens1: First list of tokens (AI snapshot — the reference set)
            tokens2: Second list of tokens (current file)

        Returns:
            Float between 0.0 (no overlap) and 1.0 (all tokens1 present in tokens2)

        Example:
            >>> normalizer = TokenNormalizer()
            >>> tokens1 = ['a', 'b', 'c']
            >>> tokens2 = ['a', 'b', 'd']
            >>> normalizer.calculate_token_overlap(tokens1, tokens2)
            0.667  # {a, b} intersection / {a, b, c} set1 = 2/3
        """
        if not tokens1 and not tokens2:
            return 1.0  # Both empty = identical

        if not tokens1 or not tokens2:
            return 0.0  # One empty = no overlap

        set1 = set(tokens1)
        set2 = set(tokens2)

        intersection = len(set1 & set2)

        return intersection / len(set1)

    def are_format_equivalent(self, text1: str, text2: str, threshold: float = 0.8) -> bool:
        """
        Check if two code sections are semantically identical (ignoring format).

        Handles 1:N, N:1, and N:M line mappings by comparing token sets.

        Args:
            text1: First code section (can be multiple lines)
            text2: Second code section (can be multiple lines)
            threshold: Minimum token overlap required (default 0.8 = 80%)

        Returns:
            True if token overlap >= threshold (likely just formatting change)
            False if token overlap < threshold (likely semantic change)

        Example:
            >>> normalizer = TokenNormalizer()
            >>> text1 = "result = calculateTotal(item1, item2, item3);"
            >>> text2 = '''result = calculateTotal(
            ...     item1,
            ...     item2,
            ...     item3
            ... );'''
            >>> normalizer.are_format_equivalent(text1, text2)
            True  # Same tokens, just different formatting
        """
        tokens1 = self.extract_tokens(text1)
        tokens2 = self.extract_tokens(text2)

        overlap = self.calculate_token_overlap(tokens1, tokens2)
        return overlap >= threshold
