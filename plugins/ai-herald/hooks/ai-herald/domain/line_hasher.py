"""Line hashing and normalization utilities."""

import hashlib


class LineHasher:
    """Handles line normalization and hashing for AI contribution tracking.

    Provides consistent hashing of code lines, normalizing whitespace
    to ensure identical semantic content produces identical hashes.
    """

    def normalize(self, line: str) -> str:
        """Normalize line by stripping leading/trailing whitespace.

        Args:
            line: Raw line content

        Returns:
            Normalized line with whitespace stripped
        """
        return line.strip()

    def hash(self, line: str, pre_normalized: bool = False) -> str:
        """Compute SHA256 hash of normalized line content.

        Args:
            line: Line content to hash
            pre_normalized: If True, skip normalization (line already normalized)

        Returns:
            SHA256 hash as hex string
        """
        normalized = line if pre_normalized else self.normalize(line)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
