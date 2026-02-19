"""GitLab CLI (glab) repository infrastructure."""

from __future__ import annotations

import json
import subprocess
from logging import Logger
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from services.mr_service import MrUpdateRequest


class GlabRepository:
    """GitLab MR operations wrapper using glab CLI.

    Handles all glab subprocess operations with timeout and error handling.
    """

    TIMEOUT_SECONDS = 10

    def __init__(self, logger: Logger):
        """Initialize glab repository.

        Args:
            logger: Logger instance for diagnostics
        """
        self._logger = logger

    def is_available(self) -> bool:
        """Check if glab CLI is installed and accessible.

        Returns:
            True if glab command is available
        """
        try:
            subprocess.run(
                ['glab', '--version'],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_mr_for_branch(self, branch: str) -> Optional[Dict]:
        """Find an open MR for the given source branch.

        Args:
            branch: Source branch name

        Returns:
            Dict with 'iid', 'title', 'description', and 'labels' keys, or None if no MR found
        """
        try:
            result = subprocess.run(
                ['glab', 'mr', 'list', '--source-branch', branch, '-F', 'json'],
                capture_output=True,
                text=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )

            mrs = json.loads(result.stdout)
            if not mrs:
                self._logger.info(f"No MR found for branch: {branch}")
                return None

            if len(mrs) > 1:
                self._logger.warning(f"Multiple MRs found for branch {branch}, using first")

            mr = mrs[0]
            return {
                'iid': str(mr['iid']),
                'title': mr['title'],
                'description': mr.get('description', ''),
                'labels': mr.get('labels', [])
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"glab mr list failed: {e}")
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            self._logger.warning(f"Failed to parse glab output: {e}")
            return None

    def add_label(self, mr_iid: str, label: str) -> bool:
        """Add a label to an MR using glab CLI.

        Args:
            mr_iid: MR internal ID (number)
            label: Label name to add

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ['glab', 'mr', 'update', mr_iid, '--label', label, '--yes'],
                capture_output=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"MR !{mr_iid} label added: {label}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"Failed to add label to MR: {e}")
            return False

    def remove_label(self, mr_iid: str, label: str) -> bool:
        """Remove a label from an MR using glab CLI.

        Args:
            mr_iid: MR internal ID (number)
            label: Label name to remove

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ['glab', 'mr', 'update', mr_iid, '--unlabel', label, '--yes'],
                capture_output=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"MR !{mr_iid} label removed: {label}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"Failed to remove label from MR: {e}")
            return False

    def update_mr_title(self, mr_iid: str, title: str) -> bool:
        """Update MR title using glab CLI.

        Args:
            mr_iid: MR internal ID (number)
            title: New title to set

        Returns:
            True if update succeeded
        """
        try:
            subprocess.run(
                ['glab', 'mr', 'update', mr_iid, '--title', title, '--yes'],
                capture_output=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"MR !{mr_iid} title updated")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"Failed to update MR title: {e}")
            return False

    def update_mr_description(self, mr_iid: str, description: str) -> bool:
        """Update MR description using glab CLI.

        Args:
            mr_iid: MR internal ID (number)
            description: New description to set

        Returns:
            True if update succeeded
        """
        try:
            subprocess.run(
                ['glab', 'mr', 'update', mr_iid, '--description', description, '--yes'],
                capture_output=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"MR !{mr_iid} description updated")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"Failed to update MR description: {e}")
            return False

    def update_mr(self, mr_iid: str, request: MrUpdateRequest) -> bool:
        """Apply all requested changes to an MR in a single glab call.

        Builds one `glab mr update` command from the request fields.
        Labels are processed as: remove old first, then add new.

        Args:
            mr_iid: MR internal ID (number)
            request: Value object describing title, description, and label changes

        Returns:
            True if the update succeeded (or nothing to update)
        """
        cmd = ['glab', 'mr', 'update', mr_iid]
        if request.title is not None:
            cmd.extend(['--title', request.title])
        if request.description is not None:
            cmd.extend(['--description', request.description])
        if request.label_to_remove is not None:
            cmd.extend(['--unlabel', request.label_to_remove])
        if request.label_to_add is not None:
            cmd.extend(['--label', request.label_to_add])
        cmd.append('--yes')

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"MR !{mr_iid} updated")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._logger.warning(f"Failed to update MR: {e}")
            return False

    def create_draft_mr(
        self,
        source_branch: str,
        title: str,
        target_branch: str,
        description: str = '',
        label: Optional[str] = None
    ) -> bool:
        """Create a draft MR using glab CLI.

        Args:
            source_branch: Source branch name
            title: MR title
            target_branch: Target branch name (e.g., 'main')
            description: MR description (default: empty string)
            label: Optional label to attach to the MR on creation

        Returns:
            True if creation succeeded
        """
        try:
            cmd = [
                'glab', 'mr', 'create',
                '--draft',
                '--title', title,
                '--source-branch', source_branch,
                '--target-branch', target_branch,
                '--description', description,
                '--yes'
            ]
            if label:
                cmd.extend(['--label', label])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.TIMEOUT_SECONDS
            )
            self._logger.info(f"Draft MR created: {source_branch} -> {target_branch}")
            return True
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else 'no stderr'
            stdout = e.stdout.strip() if e.stdout else 'no stdout'
            self._logger.warning(f"Failed to create draft MR: {e}")
            self._logger.warning(f"stderr: {stderr}")
            self._logger.warning(f"stdout: {stdout}")
            return False
        except subprocess.TimeoutExpired as e:
            self._logger.warning(f"Failed to create draft MR (timeout): {e}")
            return False
