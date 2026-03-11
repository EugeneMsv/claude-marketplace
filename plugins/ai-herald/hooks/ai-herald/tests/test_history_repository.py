"""Tests for HistoryRepository."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.history_record import HistoryExtensionStats, HistoryIgnoredStats, HistoryRecord
from infrastructure.git_repository import GitRepository
from infrastructure.history_repository import HistoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(commit_hash: str = 'abc123', branch: str = 'feature/xyz') -> HistoryRecord:
    return HistoryRecord(
        commit_hash=commit_hash,
        commit_subject='Task 1: add feature',
        committed_at='2026-02-10T14:22:00',
        branch=branch,
        author_email='alice@example.com',
        herald_version='0.0.14',
        files_changed_count=3,
        files_ai_touched_count=2,
        ai_percentage=75.0,
        ai_lines_added=90,
        ai_lines_removed=10,
        human_lines_added=30,
        human_lines_removed=5,
        by_extension={'.py': HistoryExtensionStats(ai_percentage=80.0, ai_lines=60, human_lines=15)},
        ignored=HistoryIgnoredStats(total_lines=0, lines_added=0, lines_removed=0, matched_patterns=()),
    )


def _make_git_repo(remote_url: str = 'git@github.com:alice/my-repo.git',
                   root: str = '/repos/my-repo') -> MagicMock:
    mock = MagicMock(spec=GitRepository)
    mock.get_remote_url.return_value = remote_url
    mock.get_root.return_value = Path(root)
    return mock


# ---------------------------------------------------------------------------
# Repo identity resolution
# ---------------------------------------------------------------------------

class TestResolveRepoIdentity:
    """Tests for _resolve_repo_identity and URL parsing."""

    def test_ssh_url_produces_expected_identity(self):
        """Given SSH URL, produces host_owner_repo identity."""
        # Given
        mock_git = _make_git_repo('git@github.com:alice/my-repo.git')

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity == 'github.com_alice_my-repo'

    def test_https_url_produces_expected_identity(self):
        """Given HTTPS URL, produces host_owner_repo identity."""
        # Given
        mock_git = _make_git_repo('https://github.com/alice/my-repo.git')

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity == 'github.com_alice_my-repo'

    def test_https_url_without_git_suffix(self):
        """Given HTTPS URL without .git suffix, identity is still correct."""
        # Given
        mock_git = _make_git_repo('https://gitlab.com/team/project')

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity == 'gitlab.com_team_project'

    def test_no_remote_falls_back_to_root_hash(self):
        """Given no remote URL, identity is local_ + sha256 of root path."""
        # Given
        mock_git = _make_git_repo(remote_url=None)

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity.startswith('local_')
        assert len(repo.repo_identity) == len('local_') + 16

    def test_no_remote_no_root_falls_back_to_unknown(self):
        """Given no remote and no root, identity is 'unknown'."""
        # Given
        mock_git = MagicMock(spec=GitRepository)
        mock_git.get_remote_url.return_value = None
        mock_git.get_root.return_value = None

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity == 'unknown'

    @pytest.mark.parametrize('url,expected_identity', [
        ('git@github.com:alice/my-repo.git', 'github.com_alice_my-repo'),
        ('git@gitlab.com:team/project.git', 'gitlab.com_team_project'),
        ('https://github.com/alice/my-repo.git', 'github.com_alice_my-repo'),
        ('https://gitlab.com/team/project', 'gitlab.com_team_project'),
    ])
    def test_various_url_formats(self, url: str, expected_identity: str):
        """Given various URL formats, produces correct identity."""
        # Given
        mock_git = _make_git_repo(url)

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.repo_identity == expected_identity


# ---------------------------------------------------------------------------
# File path
# ---------------------------------------------------------------------------

class TestFilePath:

    def test_file_path_uses_repo_identity_and_jsonl_extension(self):
        """Given a repo identity, file_path ends with {identity}.jsonl."""
        # Given
        mock_git = _make_git_repo('git@github.com:alice/my-repo.git')

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.file_path.name == 'github.com_alice_my-repo.jsonl'

    def test_file_path_is_inside_history_subdir(self):
        """Given a global dir, file_path is inside history/ subdirectory."""
        # Given
        mock_git = _make_git_repo()

        # When
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir)
            with patch.object(HistoryRepository, '_GLOBAL_DIR', global_dir):
                repo = HistoryRepository(mock_git)

        # Then
        assert repo.file_path.parent == global_dir / 'history'


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------

class TestAppend:

    def test_append_creates_history_directory(self):
        """Given no history directory, append() creates it."""
        # Given
        mock_git = _make_git_repo()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)
                history_dir = repo.file_path.parent
                assert not history_dir.exists()

                # When
                repo.append(_make_record())

                # Then
                assert history_dir.exists()

    def test_append_writes_jsonl_line(self):
        """Given a record, append() writes a valid JSONL line."""
        # Given
        mock_git = _make_git_repo()
        record = _make_record(commit_hash='deadbeef')

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

                # When
                repo.append(record)

                # Then
                lines = repo.file_path.read_text().splitlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data['commit_hash'] == 'deadbeef'

    def test_append_adds_newline_after_each_record(self):
        """Given two appended records, file contains two newline-terminated lines."""
        # Given
        mock_git = _make_git_repo()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

                # When
                repo.append(_make_record(commit_hash='aaa'))
                repo.append(_make_record(commit_hash='bbb'))

                # Then
                content = repo.file_path.read_text()
                lines = [l for l in content.splitlines() if l.strip()]
                assert len(lines) == 2

    def test_append_multiple_records_preserves_all(self):
        """Given three sequential appends, read_all returns all three."""
        # Given
        mock_git = _make_git_repo()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

                # When
                repo.append(_make_record(commit_hash='h1'))
                repo.append(_make_record(commit_hash='h2'))
                repo.append(_make_record(commit_hash='h3'))

                # Then
                records = repo.read_all()
                assert len(records) == 3
                hashes = {r.commit_hash for r in records}
                assert hashes == {'h1', 'h2', 'h3'}


# ---------------------------------------------------------------------------
# read_all
# ---------------------------------------------------------------------------

class TestReadAll:

    def test_read_all_returns_empty_list_when_no_file(self):
        """Given no history file, read_all() returns empty list."""
        # Given
        mock_git = _make_git_repo()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

                # When
                result = repo.read_all()

                # Then
                assert result == []

    def test_read_all_deduplicates_by_commit_hash_last_write_wins(self):
        """Given duplicate commit_hash entries, read_all() keeps last occurrence."""
        # Given
        mock_git = _make_git_repo()
        record_v1 = _make_record(commit_hash='dup', branch='feature/v1')
        record_v2 = _make_record(commit_hash='dup', branch='feature/v2')

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)
                repo.append(record_v1)
                repo.append(record_v2)

                # When
                result = repo.read_all()

                # Then
                assert len(result) == 1
                assert result[0].branch == 'feature/v2'

    def test_read_all_skips_malformed_lines(self):
        """Given a JSONL file with a malformed line, read_all() skips it."""
        # Given
        mock_git = _make_git_repo()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)
                repo.append(_make_record(commit_hash='good1'))

                # Inject a malformed line directly
                with open(repo.file_path, 'a') as f:
                    f.write('not valid json {{{\n')

                repo.append(_make_record(commit_hash='good2'))

                # When
                result = repo.read_all()

                # Then
                assert len(result) == 2
                hashes = {r.commit_hash for r in result}
                assert hashes == {'good1', 'good2'}

    def test_read_all_skips_blank_lines(self):
        """Given a JSONL file with blank lines, read_all() ignores them."""
        # Given
        mock_git = _make_git_repo()
        record = _make_record(commit_hash='abc')

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)

                # Write record with extra blank lines
                repo.file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(repo.file_path, 'w') as f:
                    f.write('\n')
                    f.write(record.to_jsonl() + '\n')
                    f.write('\n')

                # When
                result = repo.read_all()

                # Then
                assert len(result) == 1
                assert result[0].commit_hash == 'abc'

    def test_read_all_round_trip_preserves_all_fields(self):
        """Given a record written with append, read_all returns record with same fields."""
        # Given
        mock_git = _make_git_repo()
        original = _make_record(commit_hash='abc123')

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(HistoryRepository, '_GLOBAL_DIR', Path(tmpdir)):
                repo = HistoryRepository(mock_git)
                repo.append(original)

                # When
                records = repo.read_all()

                # Then
                restored = records[0]
                assert restored.commit_hash == original.commit_hash
                assert restored.ai_percentage == original.ai_percentage
                assert restored.by_extension['.py'].ai_lines == 60
                assert restored.ignored.total_lines == 0
