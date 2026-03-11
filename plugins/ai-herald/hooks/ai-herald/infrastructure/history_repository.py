"""History repository infrastructure for persistent AI contribution tracking."""

import fcntl
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from domain.history_record import HistoryRecord
from infrastructure.configuration import ConfigurationLoader
from infrastructure.git_repository import GitRepository


class HistoryRepository:
    """Repository for appending and reading per-commit history records.

    Stores one JSONL record per commit in ~/.claude/ai-herald/history/{repo-identity}.jsonl.
    Uses fcntl file locking to prevent data loss from concurrent hook invocations.
    Deduplicates by commit_hash on read (last-write-wins).
    """

    # Overridable in tests via patch.object
    _GLOBAL_DIR: Path = ConfigurationLoader.GLOBAL_DIR

    def __init__(self, git_repo: GitRepository):
        """Initialize repository, resolving storage path from the git remote.

        Args:
            git_repo: GitRepository used to determine remote URL and root.
        """
        self._repo_identity = self._resolve_repo_identity(git_repo)
        self._history_dir = self._GLOBAL_DIR / 'history'
        self._file_path = self._history_dir / f"{self._repo_identity}.jsonl"

    def _resolve_repo_identity(self, git_repo: GitRepository) -> str:
        """Derive a stable filename-safe identity from the remote URL.

        Tries to parse the git remote URL into a human-readable identity.
        Falls back to a SHA256 hash of the git root path if no remote is configured.

        Args:
            git_repo: GitRepository instance.

        Returns:
            Filename-safe identity string (e.g. 'github.com_alice_my-repo').
        """
        url = git_repo.get_remote_url()
        if url:
            parsed = self._parse_remote_url(url)
            if parsed:
                return parsed

        root = git_repo.get_root()
        if root:
            return 'local_' + hashlib.sha256(str(root).encode()).hexdigest()[:16]

        return 'unknown'

    def _parse_remote_url(self, url: str) -> Optional[str]:
        """Parse a git remote URL into a sanitized identity string.

        Handles SSH format (git@host:owner/repo.git) and
        HTTPS format (https://host/owner/repo.git).

        Args:
            url: Raw remote URL string.

        Returns:
            Sanitized identity string, or None if URL cannot be parsed.
        """
        # SSH: git@github.com:alice/my-repo.git
        ssh_match = re.match(r'^git@([^:]+):(.+?)(?:\.git)?$', url.strip())
        if ssh_match:
            host = ssh_match.group(1)
            path = ssh_match.group(2)
            return self._sanitize_identity(f"{host}_{path}")

        # HTTPS / HTTP: https://github.com/alice/my-repo.git
        try:
            parsed = urlparse(url.strip())
            if parsed.scheme in ('https', 'http') and parsed.netloc:
                path = parsed.path.lstrip('/').removesuffix('.git')
                return self._sanitize_identity(f"{parsed.netloc}_{path}")
        except Exception:
            pass

        return None

    @staticmethod
    def _sanitize_identity(raw: str) -> str:
        """Replace path-separator and special characters with underscores.

        Args:
            raw: Raw identity string.

        Returns:
            Clean filename-safe string.
        """
        sanitized = re.sub(r'[/\\:]+', '_', raw)
        sanitized = re.sub(r'_+', '_', sanitized).strip('_')
        return sanitized or 'unknown'

    def append(self, record: HistoryRecord) -> None:
        """Append one record to the JSONL history file.

        Creates the history directory if it does not exist.
        Acquires an exclusive file lock before writing to prevent
        data loss from concurrent hook invocations.

        Args:
            record: HistoryRecord to persist.
        """
        self._history_dir.mkdir(parents=True, exist_ok=True)
        with open(self._file_path, 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(record.to_jsonl() + '\n')
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read_all(self) -> List[HistoryRecord]:
        """Read all records from the JSONL history file.

        Skips malformed lines silently. Deduplicates by commit_hash,
        keeping the last occurrence (last-write-wins).

        Returns:
            List of HistoryRecord in file order, deduplicated.
        """
        if not self._file_path.exists():
            return []

        seen: Dict[str, HistoryRecord] = {}
        try:
            with open(self._file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = HistoryRecord.from_jsonl(line)
                        seen[record.commit_hash] = record
                    except (json.JSONDecodeError, KeyError):
                        continue
        except IOError:
            return []

        return list(seen.values())

    @property
    def file_path(self) -> Path:
        """Get path to the JSONL history file."""
        return self._file_path

    @property
    def repo_identity(self) -> str:
        """Get resolved repository identity string."""
        return self._repo_identity
