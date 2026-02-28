"""Git repository infrastructure."""

import subprocess
from pathlib import Path
from typing import Optional, List
from domain.diff import Diff


class GitRepository:
    """Git repository operations wrapper.

    Handles all git subprocess operations with caching for expensive calls.
    """

    def __init__(self):
        """Initialize git repository."""
        self._root: Optional[Path] = None
        self._branch: Optional[str] = None

    def get_root(self) -> Optional[Path]:
        """Get git repository root directory (cached).

        Returns:
            Path to git root, or None if not in git repo
        """
        if self._root is None:
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--show-toplevel'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self._root = Path(result.stdout.strip())
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None
        return self._root

    def get_current_branch(self) -> Optional[str]:
        """Get current git branch name (cached).

        Returns:
            Branch name, or None if not in git repo
        """
        if self._branch is None:
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self._branch = result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None
        return self._branch

    def get_merge_base(self, base_branches: List[str]) -> Optional[str]:
        """Find common ancestor commit between current branch and base branch.

        Args:
            base_branches: Priority-ordered list of base branches to try

        Returns:
            Merge-base commit hash, or None if not found
        """
        # Try each base branch in priority order
        for base_branch in base_branches:
            # Try both local and remote variants
            for branch_variant in [base_branch, f'origin/{base_branch}']:
                try:
                    result = subprocess.run(
                        ['git', 'merge-base', 'HEAD', branch_variant],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    return result.stdout.strip()
                except subprocess.CalledProcessError:
                    continue
        return None

    def resolve_target_branch(self, base_branches: List[str]) -> Optional[str]:
        """Find first existing base branch suitable as MR target.

        Traverses base_branches list in priority order, checking if each branch
        exists (trying local then origin/ remote). Returns the first branch
        that exists, without the origin/ prefix.

        Args:
            base_branches: Priority-ordered list of base branches to try

        Returns:
            Branch name (without origin/ prefix), or None if none exist
        """
        for base_branch in base_branches:
            # Try local first
            try:
                subprocess.run(
                    ['git', 'rev-parse', '--verify', base_branch],
                    capture_output=True,
                    check=True
                )
                return base_branch
            except subprocess.CalledProcessError:
                pass

            # Try remote
            try:
                subprocess.run(
                    ['git', 'rev-parse', '--verify', f'origin/{base_branch}'],
                    capture_output=True,
                    check=True
                )
                return base_branch  # Return without origin/ prefix
            except subprocess.CalledProcessError:
                continue

        return None

    def branch_exists_locally(self, branch: str) -> bool:
        """Check if branch exists in local repository.

        Args:
            branch: Branch name to check

        Returns:
            True if branch exists locally
        """
        try:
            result = subprocess.run(
                ['git', 'branch', '--list', branch],
                capture_output=True,
                text=True,
                check=True
            )
            # Branch exists if output is non-empty
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def get_diff(self, merge_base: str) -> Diff:
        """Get all changes since merge_base.

        Args:
            merge_base: Commit hash to diff against

        Returns:
            Diff object containing all file changes
        """
        try:
            result = subprocess.run(
                ['git', 'diff', '--unified=0', merge_base, 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            return Diff.from_git_output(merge_base, result.stdout)
        except subprocess.CalledProcessError:
            # Return empty diff on error
            return Diff(merge_base, {})

    def get_head_commit_hash(self) -> Optional[str]:
        """Get the current HEAD commit hash.

        Returns:
            40-character SHA hash of HEAD, or None on error
        """
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_head_commit_message(self) -> Optional[str]:
        """Get the commit message of the current HEAD commit.

        Returns:
            Commit message string, or None on error
        """
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%B'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def amend_commit_message(self, message: str) -> bool:
        """Amend the current HEAD commit with a new message.

        Args:
            message: New commit message to apply

        Returns:
            True if the amend succeeded, False otherwise
        """
        try:
            subprocess.run(
                ['git', 'commit', '--amend', '-m', message],
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def sanitize_branch_name(branch: str) -> str:
        """Sanitize branch name for use in filenames.

        Args:
            branch: Git branch name

        Returns:
            Sanitized branch name with / and \\ replaced by -
        """
        return branch.replace('/', '-').replace('\\', '-')
