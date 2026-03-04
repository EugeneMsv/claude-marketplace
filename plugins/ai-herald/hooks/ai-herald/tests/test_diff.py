"""Tests for Diff.from_git_output."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.diff import Diff


DELETED_FILE_DIFF = """\
diff --git a/settings.local.json b/settings.local.json
deleted file mode 100644
index abc1234..0000000
--- a/settings.local.json
+++ /dev/null
@@ -1,3 +0,0 @@
-{
-  "key": "value"
-}
"""

NEW_FILE_DIFF = """\
diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def hello():
+    pass
+
"""

MODIFIED_FILE_DIFF = """\
diff --git a/existing.py b/existing.py
index abc1234..def5678 100644
--- a/existing.py
+++ b/existing.py
@@ -1,3 +1,4 @@
 def foo():
-    pass
+    return 42
+
"""

MIXED_DIFF = """\
diff --git a/existing.py b/existing.py
index abc1234..def5678 100644
--- a/existing.py
+++ b/existing.py
@@ -1,2 +1,3 @@
 def foo():
-    pass
+    return 42
diff --git a/settings.local.json b/settings.local.json
deleted file mode 100644
index abc1234..0000000
--- a/settings.local.json
+++ /dev/null
@@ -1,2 +0,0 @@
-{
-  "key": "value"
-}
"""


def test_deleted_file():
    # Given a diff where a file is deleted ("+++ /dev/null")
    diff = Diff.from_git_output("abc123", DELETED_FILE_DIFF)

    # When checking changed files
    changed = diff.get_changed_files()

    # Then the deleted file is tracked
    assert "settings.local.json" in changed
    file_diff = diff.get_file_diff("settings.local.json")
    assert file_diff is not None
    assert file_diff.get_removed_count() == 3
    assert file_diff.get_added_count() == 0


def test_new_file():
    # Given a diff where a new file is added ("--- /dev/null")
    diff = Diff.from_git_output("abc123", NEW_FILE_DIFF)

    # When checking changed files
    changed = diff.get_changed_files()

    # Then the new file is tracked
    assert "new_file.py" in changed
    file_diff = diff.get_file_diff("new_file.py")
    assert file_diff is not None
    assert file_diff.get_added_count() == 3
    assert file_diff.get_removed_count() == 0


def test_modified_file():
    # Given a diff where a file is modified
    diff = Diff.from_git_output("abc123", MODIFIED_FILE_DIFF)

    # When checking changed files
    changed = diff.get_changed_files()

    # Then both added and removed lines are captured
    assert "existing.py" in changed
    file_diff = diff.get_file_diff("existing.py")
    assert file_diff is not None
    assert file_diff.get_added_count() == 2
    assert file_diff.get_removed_count() == 1


def test_mixed_diff_modified_and_deleted():
    # Given a diff containing both a modified and a deleted file
    diff = Diff.from_git_output("abc123", MIXED_DIFF)

    changed = diff.get_changed_files()

    # Both files are present without cross-contamination
    assert "existing.py" in changed
    assert "settings.local.json" in changed

    modified = diff.get_file_diff("existing.py")
    assert modified is not None
    assert modified.get_added_count() == 1
    assert modified.get_removed_count() == 1

    deleted = diff.get_file_diff("settings.local.json")
    assert deleted is not None
    assert deleted.get_removed_count() == 3
    assert deleted.get_added_count() == 0
