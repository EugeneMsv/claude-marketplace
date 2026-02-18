"""
Format snapshot data model for capturing pre-format state.

This module defines the data structure for temporary snapshots created
before code formatters run. Snapshots store AI-attributed line content
so it can be compared with post-format state.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class FormatSnapshot:
    """
    Represents a temporary snapshot of file state before formatting.

    This snapshot is created by PreToolUse hook and consumed by PostToolUse hook.
    It stores the content of AI-attributed lines so they can be matched against
    formatted output using token comparison.

    Attributes:
        pid: Process ID of the formatting command
        branch: Current git branch name
        timestamp: When snapshot was created (ISO format)
        files: Mapping of file_path → {hash → content}
               Example: {
                   "src/Main.java": {
                       "hash_abc123": "result = calculate(x, y);"
                   }
               }
    """

    pid: int
    branch: str
    timestamp: str
    files: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert snapshot to dictionary for JSON serialization."""
        return {
            "pid": self.pid,
            "branch": self.branch,
            "timestamp": self.timestamp,
            "files": self.files
        }

    @staticmethod
    def from_dict(data: dict) -> 'FormatSnapshot':
        """Create snapshot from dictionary (JSON deserialization)."""
        return FormatSnapshot(
            pid=data["pid"],
            branch=data["branch"],
            timestamp=data["timestamp"],
            files=data.get("files", {})
        )

    def to_json(self) -> str:
        """Serialize snapshot to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_json(json_str: str) -> 'FormatSnapshot':
        """Deserialize snapshot from JSON string."""
        data = json.loads(json_str)
        return FormatSnapshot.from_dict(data)

    def save_to_file(self, file_path: str) -> None:
        """
        Save snapshot to file using atomic write.

        Args:
            file_path: Path where snapshot should be saved
        """
        # Write to temporary file first (atomic write)
        temp_path = f"{file_path}.tmp"
        try:
            with open(temp_path, 'w') as f:
                f.write(self.to_json())
            # Atomic rename
            os.rename(temp_path, file_path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    @staticmethod
    def load_from_file(file_path: str) -> 'FormatSnapshot':
        """
        Load snapshot from file.

        Args:
            file_path: Path to snapshot file

        Returns:
            FormatSnapshot instance

        Raises:
            FileNotFoundError: If snapshot file doesn't exist
            json.JSONDecodeError: If snapshot file is corrupted
        """
        with open(file_path, 'r') as f:
            return FormatSnapshot.from_json(f.read())

    def add_file_content(self, file_path: str, hash_to_content: Dict[str, str]) -> None:
        """
        Add AI-attributed line content for a file.

        Args:
            file_path: Relative path to file from git root
            hash_to_content: Mapping of line hash → line content
        """
        if file_path not in self.files:
            self.files[file_path] = {}
        self.files[file_path].update(hash_to_content)

    def get_file_content(self, file_path: str) -> Dict[str, str]:
        """
        Get AI-attributed line content for a file.

        Args:
            file_path: Relative path to file from git root

        Returns:
            Mapping of line hash → line content (empty dict if file not in snapshot)
        """
        return self.files.get(file_path, {})

    @staticmethod
    def create_new(pid: int, branch: str) -> 'FormatSnapshot':
        """
        Create a new snapshot with current timestamp.

        Args:
            pid: Process ID of formatting command
            branch: Current git branch name

        Returns:
            New FormatSnapshot instance
        """
        return FormatSnapshot(
            pid=pid,
            branch=branch,
            timestamp=datetime.utcnow().isoformat(),
            files={}
        )
