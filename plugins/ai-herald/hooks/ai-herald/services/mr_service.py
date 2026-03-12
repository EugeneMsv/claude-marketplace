"""MR service for AI contribution tracking."""

import re
from dataclasses import dataclass
from logging import Logger
from typing import Optional
from domain.contribution_stats import ContributionStats
from infrastructure.git_repository import GitRepository
from infrastructure.glab_repository import GlabRepository, MrInfo
from infrastructure.configuration import Configuration
from infrastructure.tracking_repository import TrackingRepository


@dataclass
class MrUpdateRequest:
    """Value object describing all changes to apply in a single glab mr update call."""

    title: Optional[str] = None
    description: Optional[str] = None
    label_to_add: Optional[str] = None
    label_to_remove: Optional[str] = None

    def is_empty(self) -> bool:
        """Return True when no fields are set (nothing to update)."""
        return all(v is None for v in [self.title, self.description, self.label_to_add, self.label_to_remove])
STATS_TAG_PATTERN = re.compile(r'\s*\[AI:\s*\d+%\]')
STATS_SECTION_PATTERN = re.compile(r'## AI Contribution Stats\s*```[^`]*```', re.MULTILINE | re.DOTALL)
TICKET_PATTERN = re.compile(r'([A-Z]+-\d+)', re.IGNORECASE)
AI_LABEL_PATTERN = re.compile(r'^AI:\d+%$')


class MrResult:
    """Result of processing a git push for MR updates."""

    def __init__(self, success: bool, ai_percentage: Optional[int] = None, message: Optional[str] = None):
        """Initialize MR result.

        Args:
            success: Whether MR was successfully updated/created
            ai_percentage: AI contribution percentage (0-100), None if failed
            message: Optional informational message to show user
        """
        self.success = success
        self.ai_percentage = ai_percentage
        self.message = message


class MrService:
    """Service coordinating MR updates with AI contribution stats.

    Processes git push events to update MR titles with compact stats.
    Reads pre-calculated stats from tracking data (written by inject hook on commit).
    """

    def __init__(
        self,
        git_repo: GitRepository,
        glab_repo: GlabRepository,
        config: Configuration,
        logger: Logger
    ):
        """Initialize MR service.

        Args:
            git_repo: GitRepository for git operations
            glab_repo: GlabRepository for GitLab CLI operations
            config: Configuration settings
            logger: Logger instance with hook context
        """
        self._git_repo = git_repo
        self._glab_repo = glab_repo
        self._config = config
        self._logger = logger

    def process_push(self) -> MrResult:
        """Process a git push event.

        Caller is responsible for routing: only invoke when a non-tag git push
        was detected and all feature flags are enabled.

        Returns:
            MrResult with success status and AI percentage if successful
        """
        if not self._config.mr_features_enabled:
            self._logger.info("All MR features disabled in config")
            return MrResult(False)

        self._logger.info("Git push command detected")

        # Get current branch
        branch = self._git_repo.get_current_branch()
        if not branch:
            self._logger.warning("Could not get current branch")
            return MrResult(False)

        self._logger.info(f"Current branch: {branch}")

        # Check for MR
        mr = self._glab_repo.get_mr_for_branch(branch)
        if not mr:
            self._logger.info(f"No MR found for branch {branch}")
            # Auto-create draft MR if enabled
            if self._config.mr_auto_creation_enabled:
                return self._auto_create_mr(branch)
            self._logger.info("Auto-creation disabled, skipping")
            return MrResult(False, message="ℹ️ No MR found (auto-creation disabled)")

        self._logger.info(f"Found MR !{mr.iid}: {mr.title}")

        # Load tracking data with pre-calculated stats
        git_root = self._git_repo.get_root()
        if not git_root:
            self._logger.warning("Could not get git root directory")
            return MrResult(False)

        sanitized_branch = self._git_repo.sanitize_branch_name(branch)
        tracking_repo = TrackingRepository(git_root, sanitized_branch)

        tracking = tracking_repo.load()
        if not tracking or not tracking.stats:
            self._logger.warning("No tracking data or stats found")
            return MrResult(False, message="ℹ️ No AI contributions tracked yet")

        # Reconstruct stats from saved tracking data
        stats = ContributionStats.from_dict(tracking.stats)
        self._logger.info(f"Stats from tracking: {stats.format_compact()}")

        # Build update request — each helper owns its flag check
        update_request = MrUpdateRequest()
        self._apply_title_update(mr, stats, update_request)
        self._apply_description_update(mr, stats, update_request)
        self._apply_label_update(mr, stats, update_request)

        if update_request.is_empty():
            self._logger.info("No MR changes requested by active flags")
            return MrResult(False)

        success = self._glab_repo.update_mr(mr.iid, update_request)
        if success:
            self._logger.info("=== MR updated ===")
        ai_percentage = int(round(stats.ai_percentage)) if success else None
        result = MrResult(success, ai_percentage)
        if result.success:
            self._logger.info("MR updated successfully")
        else:
            self._logger.info("Skipped (not applicable)")
        return result

    def _auto_create_mr(self, branch: str) -> MrResult:
        """Auto-create draft MR for branch.

        Args:
            branch: Source branch name

        Returns:
            MrResult with success status and AI percentage if successful
        """
        self._logger.info("Auto-creating draft MR")

        # Resolve target branch
        target_branch = self._git_repo.resolve_target_branch(self._config.base_branches)
        if not target_branch:
            self._logger.warning("Could not resolve target branch")
            return MrResult(False, message="⚠️ Could not create MR (target branch unknown)")

        self._logger.info(f"Target branch: {target_branch}")

        # Derive title from branch name
        title = self._derive_title_from_branch(branch)
        self._logger.info(f"Derived title: {title}")

        # Enrich MR with AI stats based on active flags
        description = ''
        ai_percentage = None
        create_label = None
        git_root = self._git_repo.get_root()
        if git_root:
            sanitized_branch = self._git_repo.sanitize_branch_name(branch)
            tracking_repo = TrackingRepository(git_root, sanitized_branch)
            tracking = tracking_repo.load()

            if tracking and tracking.stats:
                stats = ContributionStats.from_dict(tracking.stats)
                ai_percentage = int(round(stats.ai_percentage))

                if self._config.mr_title_update_enabled:
                    stats_tag = stats.format_compact()
                    title = f"{title} {stats_tag}"
                    self._logger.info(f"Added AI stats to title: {stats_tag}")

                if self._config.mr_description_update_enabled:
                    description = stats.format_description()
                    self._logger.info("Added AI stats to description")

                if self._config.mr_labeling_enabled:
                    create_label = self._ai_label(stats)

        # Create draft MR
        success = self._glab_repo.create_draft_mr(branch, title, target_branch, description, label=create_label)
        if success:
            self._logger.info(f"=== Draft MR created: {title} ===")
            # Show message if MR created without stats
            if ai_percentage is None:
                return MrResult(success, None, message=f"✓ Draft MR created: {title}")
        return MrResult(success, ai_percentage)

    def _apply_title_update(self, mr: MrInfo, stats: ContributionStats, request: MrUpdateRequest) -> None:
        """Populate request.title if title update is enabled and title would change."""
        if not self._config.mr_title_update_enabled:
            return
        new_title = self._build_new_title(mr.title, stats)
        if new_title != mr.title:
            request.title = new_title
        else:
            self._logger.info("Title unchanged, skipping title update")

    def _apply_description_update(self, mr: MrInfo, stats: ContributionStats, request: MrUpdateRequest) -> None:
        """Populate request.description if description update is enabled and description would change."""
        if not self._config.mr_description_update_enabled:
            return
        new_description = self._merge_description(mr.description, stats)
        if new_description != mr.description:
            request.description = new_description
        else:
            self._logger.info("Description unchanged, skipping description update")

    def _apply_label_update(self, mr: MrInfo, stats: ContributionStats, request: MrUpdateRequest) -> None:
        """Populate request label fields if labeling is enabled and label would change."""
        if not self._config.mr_labeling_enabled:
            return
        new_label = self._ai_label(stats)
        existing_ai_label = next(
            (lbl for lbl in mr.labels if AI_LABEL_PATTERN.match(lbl)),
            None
        )
        if existing_ai_label is None:
            request.label_to_add = new_label
        elif existing_ai_label != new_label:
            request.label_to_remove = existing_ai_label
            request.label_to_add = new_label
        else:
            self._logger.info(f"AI label unchanged: {new_label}")

    @staticmethod
    def _derive_title_from_branch(branch: str) -> str:
        """Derive MR title from branch name.

        Extracts Jira ticket (uppercase), strips prefix before slash,
        humanizes remaining text.

        Args:
            branch: Branch name (e.g., "feature/PROJ-12345-add-login")

        Returns:
            Humanized title (e.g., "PROJ-12345 Add login")
        """
        # Extract ticket
        ticket_match = TICKET_PATTERN.search(branch)
        if ticket_match:
            ticket = ticket_match.group(1).upper()
            original_ticket = ticket_match.group(1)
        else:
            ticket = None
            original_ticket = None

        # Strip prefix before slash
        if '/' in branch:
            text = branch.split('/', 1)[1]
        else:
            text = branch

        # Remove ticket from text (using original case for replacement)
        if original_ticket:
            text = text.replace(original_ticket, '').strip('-_')

        # Humanize: replace - and _ with spaces, capitalize first word
        text = text.replace('-', ' ').replace('_', ' ').strip()
        if text:
            text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

        # Build title
        if ticket and text:
            return f"{ticket} {text}"
        elif ticket:
            return ticket
        elif text:
            return text
        else:
            return branch

    @staticmethod
    def _build_new_title(current_title: str, stats: ContributionStats) -> str:
        """Build new MR title with compact stats tag.

        Strips existing [AI: X%] tag if present, appends new one.

        Args:
            current_title: Current MR title
            stats: Calculated contribution stats

        Returns:
            New title with stats tag appended
        """
        clean_title = STATS_TAG_PATTERN.sub('', current_title).strip()
        tag = stats.format_compact()
        if clean_title:
            return f"{clean_title} {tag}"
        return tag

    @staticmethod
    def _ai_label(stats: ContributionStats) -> str:
        """Build AI label string from contribution stats.

        Args:
            stats: Contribution stats

        Returns:
            Label string like 'AI:85%'
        """
        return f"AI:{int(round(stats.ai_percentage))}%"

    @staticmethod
    def _merge_description(current_description: str, stats: ContributionStats) -> str:
        """Merge AI stats into MR description, preserving existing content.

        Strips existing stats section if present, appends new stats section.

        Args:
            current_description: Current MR description
            stats: Calculated contribution stats

        Returns:
            New description with stats section appended
        """
        # Strip existing stats section
        clean_description = STATS_SECTION_PATTERN.sub('', current_description).strip()

        # Build new stats section
        stats_section = stats.format_description()

        # Combine: existing content + stats
        if clean_description:
            return f"{clean_description}\n\n{stats_section}"
        return stats_section
