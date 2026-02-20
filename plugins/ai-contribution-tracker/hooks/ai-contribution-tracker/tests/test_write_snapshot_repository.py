"""Tests for WriteSnapshotRepository."""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.write_snapshot_repository import WriteSnapshotRepository


class TestSaveAndLoad:
    """Tests for save() + load_and_delete() round-trip."""

    def test_round_trip_returns_saved_content(self):
        """Given saved content, load_and_delete returns exact same content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            file_path = '/some/project/src/app.py'

            repo.save(file_path, 'def foo():\n    return 1\n')
            result = repo.load_and_delete(file_path)

            assert result == 'def foo():\n    return 1\n'

    def test_round_trip_empty_content(self):
        """Given empty content (new file), load_and_delete returns ''."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))

            repo.save('/project/new_file.py', '')
            result = repo.load_and_delete('/project/new_file.py')

            assert result == ''

    def test_snapshot_deleted_after_load(self):
        """load_and_delete removes the snapshot file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            file_path = '/some/file.py'

            repo.save(file_path, 'content')
            repo.load_and_delete(file_path)
            second_load = repo.load_and_delete(file_path)

            assert second_load == ''

    def test_different_paths_produce_different_snapshots(self):
        """Two different file paths are stored independently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))

            repo.save('/project/a.py', 'content A')
            repo.save('/project/b.py', 'content B')

            assert repo.load_and_delete('/project/a.py') == 'content A'
            assert repo.load_and_delete('/project/b.py') == 'content B'


class TestMissingSnapshot:
    """Tests for load_and_delete when no snapshot exists."""

    def test_load_missing_returns_empty_string(self):
        """load_and_delete returns '' when no snapshot exists for the path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            result = repo.load_and_delete('/no/snapshot/here.py')
            assert result == ''

    def test_load_after_never_saved_returns_empty_string(self):
        """Given nothing was ever saved, load_and_delete returns ''."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            assert repo.load_and_delete('/project/app.py') == ''


class TestDirectoryCreation:
    """Tests for automatic directory creation."""

    def test_save_creates_snapshots_directory(self):
        """save() creates .claude/write-snapshots/ if it does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            snapshot_dir = Path(tmpdir) / '.claude' / 'write-snapshots'

            assert not snapshot_dir.exists()
            repo.save('/project/app.py', 'content')
            assert snapshot_dir.exists()

    def test_save_returns_true_on_success(self):
        """save() returns True when snapshot is written successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = WriteSnapshotRepository(Path(tmpdir))
            result = repo.save('/project/app.py', 'content')
            assert result is True


class TestNullGitRoot:
    """Tests for graceful handling when git root is None."""

    def test_save_returns_false_when_no_git_root(self):
        """save() returns False when git_root is None."""
        repo = WriteSnapshotRepository(None)
        assert repo.save('/project/app.py', 'content') is False

    def test_load_returns_empty_string_when_no_git_root(self):
        """load_and_delete returns '' when git_root is None."""
        repo = WriteSnapshotRepository(None)
        assert repo.load_and_delete('/project/app.py') == ''
