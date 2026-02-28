"""Tests for TrackingRepository."""

import sys
from pathlib import Path
import pytest
import json
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.tracking_repository import TrackingRepository
from domain.tracking_data import TrackingData
from domain.line_hasher import LineHasher


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def hasher():
    return LineHasher()


@pytest.fixture
def tracking_repo(temp_dir):
    return TrackingRepository(temp_dir, "test-branch")


class TestSaveAndLoad:
    """Tests for save and load operations."""

    def test_save_creates_file(self, tracking_repo, temp_dir):
        """Given tracking data, creates JSON file."""
        tracking = TrackingData("test-branch")
        tracking.files_tracked = ["file.py"]

        success = tracking_repo.save(tracking)

        assert success
        assert tracking_repo.tracking_path.exists()

    def test_load_nonexistent_returns_none(self, tracking_repo):
        """Given no tracking file, returns None."""
        tracking = tracking_repo.load()
        assert tracking is None

    def test_save_and_load_roundtrip(self, tracking_repo, hasher):
        """Given tracking data with hash counts, roundtrip preserves data."""
        tracking = TrackingData("test-branch")
        tracking.merge_base = "abc123"
        tracking.files_tracked = ["file1.py", "file2.py"]
        tracking.add_ai_lines("file1.py", ["line A", "line A", "line B"], hasher)
        tracking.track_ai_removals("file2.py", ["removed"], hasher)

        # Save
        success = tracking_repo.save(tracking)
        assert success

        # Load
        loaded = tracking_repo.load()
        assert loaded is not None
        assert loaded.branch == "test-branch"
        assert loaded.merge_base == "abc123"
        assert loaded.files_tracked == ["file1.py", "file2.py"]

        # Verify hash counts preserved
        hashes1 = loaded.get_ai_hashes_for_file("file1.py")
        line_a_hash = hasher.hash("line A")
        line_b_hash = hasher.hash("line B")
        assert hashes1[line_a_hash] == 2
        assert hashes1[line_b_hash] == 1

        removed = loaded.get_ai_removed_hashes_for_file("file2.py")
        removed_hash = hasher.hash("removed")
        assert removed[removed_hash] == 1

    def test_save_new_format_structure(self, tracking_repo, hasher):
        """Given tracking data, saves as dict with counts (new format)."""
        tracking = TrackingData("test-branch")
        tracking.add_ai_lines("file.py", ["line A", "line A"], hasher)

        tracking_repo.save(tracking)

        # Read raw JSON
        with open(tracking_repo.tracking_path, 'r') as f:
            data = json.load(f)

        # Verify structure is dict, not list
        assert "ai_line_hashes" in data
        assert "file.py" in data["ai_line_hashes"]
        file_hashes = data["ai_line_hashes"]["file.py"]

        # New format: should be dict with counts
        assert isinstance(file_hashes, dict)
        line_a_hash = hasher.hash("line A")
        assert file_hashes[line_a_hash] == 2


class TestMigration:
    """Tests for old format to new format migration."""

    def test_migrate_old_format_list_to_dict(self, tracking_repo, hasher):
        """Given old format (list of hashes), migrates to new format (dict with counts)."""
        # Create old format JSON manually
        line_a_hash = hasher.hash("line A")
        line_b_hash = hasher.hash("line B")

        old_format_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": ["file.py"],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {
                "file.py": [line_a_hash, line_b_hash]  # Old format: list
            },
            "ai_removed_line_hashes": {}
        }

        # Write old format file
        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            json.dump(old_format_data, f)

        # Load and verify migration
        tracking = tracking_repo.load()
        assert tracking is not None

        hashes = tracking.get_ai_hashes_for_file("file.py")
        # Migrated from list: each hash gets count=1
        assert hashes[line_a_hash] == 1
        assert hashes[line_b_hash] == 1

    def test_migrate_preserves_new_format(self, tracking_repo, hasher):
        """Given new format (dict with counts), preserves counts."""
        line_a_hash = hasher.hash("line A")
        line_b_hash = hasher.hash("line B")

        new_format_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": ["file.py"],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {
                "file.py": {line_a_hash: 3, line_b_hash: 1}  # New format: dict with counts
            },
            "ai_removed_line_hashes": {}
        }

        # Write new format file
        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            json.dump(new_format_data, f)

        # Load and verify counts preserved
        tracking = tracking_repo.load()
        assert tracking is not None

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert hashes[line_a_hash] == 3
        assert hashes[line_b_hash] == 1

    def test_migrate_handles_empty_list(self, tracking_repo):
        """Given empty list in old format, migrates to empty dict."""
        old_format_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": [],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {
                "file.py": []  # Empty list
            },
            "ai_removed_line_hashes": {}
        }

        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            json.dump(old_format_data, f)

        tracking = tracking_repo.load()
        assert tracking is not None

        hashes = tracking.get_ai_hashes_for_file("file.py")
        assert hashes == {}

    def test_migrate_removed_hashes(self, tracking_repo, hasher):
        """Given old format with removed hashes, migrates correctly."""
        removed_hash = hasher.hash("removed line")

        old_format_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": [],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {},
            "ai_removed_line_hashes": {
                "file.py": [removed_hash]  # Old format: list
            }
        }

        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            json.dump(old_format_data, f)

        tracking = tracking_repo.load()
        removed = tracking.get_ai_removed_hashes_for_file("file.py")
        assert removed[removed_hash] == 1


class TestPendingInjectHead:
    """Tests for pending_inject_head field persistence."""

    def test_pending_inject_head_roundtrip(self, tracking_repo):
        """Given pending_inject_head set, roundtrip preserves value."""
        tracking = TrackingData("test-branch")
        tracking.pending_inject_head = "abc123def456"

        tracking_repo.save(tracking)
        loaded = tracking_repo.load()

        assert loaded is not None
        assert loaded.pending_inject_head == "abc123def456"

    def test_pending_inject_head_defaults_to_none(self, tracking_repo):
        """Given tracking data without pending_inject_head, loads as None."""
        tracking = TrackingData("test-branch")
        tracking_repo.save(tracking)
        loaded = tracking_repo.load()

        assert loaded is not None
        assert loaded.pending_inject_head is None

    def test_pending_inject_head_absent_in_old_file_loads_as_none(self, tracking_repo):
        """Given old tracking file without pending_inject_head key, loads as None."""
        old_data = {
            "branch": "test-branch",
            "merge_base": None,
            "files_tracked": [],
            "stats": None,
            "last_updated": None,
            "ai_line_hashes": {},
            "ai_removed_line_hashes": {}
        }

        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            json.dump(old_data, f)

        loaded = tracking_repo.load()

        assert loaded is not None
        assert loaded.pending_inject_head is None

    def test_pending_inject_head_cleared_to_none_saves_none(self, tracking_repo):
        """Given pending_inject_head set then cleared, roundtrip preserves None."""
        tracking = TrackingData("test-branch")
        tracking.pending_inject_head = "abc123"
        tracking_repo.save(tracking)

        tracking.pending_inject_head = None
        tracking_repo.save(tracking)

        loaded = tracking_repo.load()
        assert loaded.pending_inject_head is None


class TestErrorHandling:
    """Tests for error handling."""

    def test_load_invalid_json_returns_none(self, tracking_repo):
        """Given invalid JSON, returns None."""
        tracking_repo.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracking_repo.tracking_path, 'w') as f:
            f.write("{invalid json")

        tracking = tracking_repo.load()
        assert tracking is None

    def test_exists_returns_false_when_missing(self, tracking_repo):
        """Given no tracking file, exists returns False."""
        assert not tracking_repo.exists()

    def test_exists_returns_true_when_present(self, tracking_repo):
        """Given tracking file exists, exists returns True."""
        tracking = TrackingData("test-branch")
        tracking_repo.save(tracking)
        assert tracking_repo.exists()
