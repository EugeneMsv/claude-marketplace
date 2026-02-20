"""Tests for MrService."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import (
    ContributionStats,
    ContributorStats,
    LineStats,
)
from infrastructure.glab_repository import MrInfo
from services.mr_service import MrService


def _make_stats(ai_pct: float) -> ContributionStats:
    """Helper to create ContributionStats with given AI total percentage."""
    ai = ContributorStats(
        total=LineStats(lines=10, percentage=ai_pct),
        added=LineStats(lines=10, percentage=ai_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    human = ContributorStats(
        total=LineStats(lines=5, percentage=100.0 - ai_pct),
        added=LineStats(lines=5, percentage=100.0 - ai_pct),
        removed=LineStats(lines=0, percentage=0.0),
    )
    return ContributionStats(ai_stats=ai, human_stats=human, by_file_type={})


class TestBuildNewTitle:

    def test_appends_tag_to_clean_title(self):
        """Given title without tag, appends [AI: X%]."""
        stats = _make_stats(85.0)
        result = MrService._build_new_title("Add feature X", stats)
        assert result == "Add feature X [AI: 85%]"

    def test_replaces_existing_tag(self):
        """Given title with existing tag, replaces it."""
        stats = _make_stats(90.0)
        result = MrService._build_new_title("Add feature X [AI: 85%]", stats)
        assert result == "Add feature X [AI: 90%]"

    def test_replaces_tag_with_different_spacing(self):
        """Given title with oddly spaced tag, replaces correctly."""
        stats = _make_stats(75.0)
        result = MrService._build_new_title("Add feature X  [AI:  50%]", stats)
        assert result == "Add feature X [AI: 75%]"

    def test_zero_percent(self):
        """Given 0% AI contribution, appends [AI: 0%]."""
        stats = _make_stats(0.0)
        result = MrService._build_new_title("Manual changes", stats)
        assert result == "Manual changes [AI: 0%]"

    def test_hundred_percent(self):
        """Given 100% AI contribution, appends [AI: 100%]."""
        stats = _make_stats(100.0)
        result = MrService._build_new_title("Full AI", stats)
        assert result == "Full AI [AI: 100%]"

    def test_empty_title(self):
        """Given empty title, returns just the tag."""
        stats = _make_stats(50.0)
        result = MrService._build_new_title("", stats)
        assert result == "[AI: 50%]"

    def test_title_only_tag(self):
        """Given title that is only the tag, replaces cleanly."""
        stats = _make_stats(60.0)
        result = MrService._build_new_title("[AI: 30%]", stats)
        assert result == "[AI: 60%]"


class TestDeriveTitleFromBranch:

    def test_extracts_ticket_and_humanizes(self):
        """Given branch with prefix, ticket, and description, derives clean title."""
        result = MrService._derive_title_from_branch("feature/PROJ-12345-add-login")
        assert result == "PROJ-12345 Add login"

    def test_handles_underscores(self):
        """Given branch with underscores, replaces with spaces."""
        result = MrService._derive_title_from_branch("bugfix/PROJ-999-fix_user_auth")
        assert result == "PROJ-999 Fix user auth"

    def test_handles_mixed_separators(self):
        """Given branch with mixed separators, normalizes to spaces."""
        result = MrService._derive_title_from_branch("story/ABC-1-some_mixed-text")
        assert result == "ABC-1 Some mixed text"

    def test_handles_no_prefix(self):
        """Given branch without prefix, still extracts ticket."""
        result = MrService._derive_title_from_branch("PROJ-456-direct-branch")
        assert result == "PROJ-456 Direct branch"

    def test_handles_no_ticket(self):
        """Given branch without ticket, humanizes branch name."""
        result = MrService._derive_title_from_branch("feature/some-feature-name")
        assert result == "Some feature name"

    def test_handles_ticket_only(self):
        """Given branch with only ticket, returns ticket."""
        result = MrService._derive_title_from_branch("feature/PROJ-789")
        assert result == "PROJ-789"

    def test_handles_no_slash(self):
        """Given branch without slash, processes as-is."""
        result = MrService._derive_title_from_branch("some-branch")
        assert result == "Some branch"

    def test_uppercase_ticket(self):
        """Given lowercase ticket, converts to uppercase."""
        result = MrService._derive_title_from_branch("feature/proj-123-test")
        assert result == "PROJ-123 Test"

    def test_multiple_words(self):
        """Given multi-word description, capitalizes only first."""
        result = MrService._derive_title_from_branch("feature/PROJ-1-add-new-payment-method")
        assert result == "PROJ-1 Add new payment method"

    def test_empty_after_ticket(self):
        """Given only prefix and ticket, returns ticket."""
        result = MrService._derive_title_from_branch("hotfix/BUG-42")
        assert result == "BUG-42"

    def test_fallback_to_branch_name(self):
        """Given unparseable branch, returns as-is."""
        result = MrService._derive_title_from_branch("weird")
        assert result == "Weird"


class TestMergeDescription:

    def test_empty_description(self):
        """Given empty description, returns just stats section."""
        stats = _make_stats(85.0)
        result = MrService._merge_description("", stats)
        assert result.startswith("## AI Contribution Stats")
        assert "```" in result

    def test_description_without_stats(self):
        """Given description without stats, appends stats section."""
        stats = _make_stats(90.0)
        result = MrService._merge_description("This is my MR\n\nIt does something cool", stats)
        assert result.startswith("This is my MR\n\nIt does something cool")
        assert "## AI Contribution Stats" in result
        assert result.count("## AI Contribution Stats") == 1

    def test_description_with_existing_stats(self):
        """Given description with existing stats, replaces stats section."""
        stats = _make_stats(75.0)
        old_description = "My feature\n\n## AI Contribution Stats\n\n```\nOld stats\n```\n\nMore text"
        result = MrService._merge_description(old_description, stats)
        assert "My feature" in result
        assert "More text" in result
        assert "Old stats" not in result
        assert "## AI Contribution Stats" in result
        assert result.count("## AI Contribution Stats") == 1

    def test_preserves_multiple_paragraphs(self):
        """Given description with multiple paragraphs, preserves all."""
        stats = _make_stats(80.0)
        description = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        result = MrService._merge_description(description, stats)
        assert "Paragraph 1" in result
        assert "Paragraph 2" in result
        assert "Paragraph 3" in result
        assert "## AI Contribution Stats" in result


class TestAiLabel:

    @pytest.mark.parametrize("ai_pct,expected_label", [
        (85.4, "AI:85%"),
        (85.6, "AI:86%"),
        (100.0, "AI:100%"),
        (0.0, "AI:0%"),
        (50.0, "AI:50%"),
    ])
    def test_formats_label_with_rounded_integer(self, ai_pct, expected_label):
        """Given AI percentage, _ai_label returns correctly formatted label."""
        stats = _make_stats(ai_pct)
        assert MrService._ai_label(stats) == expected_label


def _make_service(
    labeling_enabled=False,
    title_update=True,
    description_update=True,
    auto_creation=True,
):
    """Build an MrService with mocked dependencies."""
    git_repo = MagicMock()
    glab_repo = MagicMock()
    config = MagicMock()
    config.mr_labeling_enabled = labeling_enabled
    config.mr_title_update_enabled = title_update
    config.mr_description_update_enabled = description_update
    config.mr_auto_creation_enabled = auto_creation
    config.base_branches = ["main"]
    logger = logging.getLogger("test")
    return MrService(git_repo, glab_repo, config, logger), git_repo, glab_repo, config


def _make_tracking_mock(ai_pct: float):
    """Build a mock TrackingData with stats for given AI percentage."""
    stats = _make_stats(ai_pct)
    tracking = MagicMock()
    tracking.stats = stats.to_dict() if hasattr(stats, 'to_dict') else {
        'ai': {
            'total': {'lines': 10, 'percentage': ai_pct},
            'added': {'lines': 10, 'percentage': ai_pct},
            'removed': {'lines': 0, 'percentage': 0.0},
        },
        'human': {
            'total': {'lines': 5, 'percentage': 100.0 - ai_pct},
            'added': {'lines': 5, 'percentage': 100.0 - ai_pct},
            'removed': {'lines': 0, 'percentage': 0.0},
        },
        'by_file_type': {}
    }
    return tracking


class TestProcessPushFlagIndependence:
    """Tests verifying T/D/L flags are fully independent in process_push."""

    def _setup(self, service, git_repo, glab_repo, existing_labels=None, ai_pct=85.0, title="My MR"):
        """Wire up mocks for a successful process_push run."""
        git_repo.get_current_branch.return_value = "feature/test"
        glab_repo.get_mr_for_branch.return_value = MrInfo(
            iid='42',
            title=title,
            description='',
            labels=existing_labels or [],
        )
        git_repo.get_root.return_value = Path("/fake/root")
        glab_repo.update_mr.return_value = True
        return _make_tracking_mock(ai_pct)

    def _get_update_request(self, glab_repo):
        """Extract the MrUpdateRequest passed to update_mr."""
        assert glab_repo.update_mr.called, "update_mr was not called"
        return glab_repo.update_mr.call_args[0][1]

    # --- Title flag ---

    @patch("services.mr_service.TrackingRepository")
    def test_title_set_when_title_update_enabled(self, mock_tracking_cls):
        """Given title_update=True, request.title is populated."""
        service, git_repo, glab_repo, _ = _make_service(title_update=True, description_update=False, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.title is not None
        assert req.description is None
        assert req.label_to_add is None

    @patch("services.mr_service.TrackingRepository")
    def test_title_not_set_when_title_update_disabled(self, mock_tracking_cls):
        """Given title_update=False, request.title is None."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=True, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.title is None
        assert req.description is not None

    # --- Description flag ---

    @patch("services.mr_service.TrackingRepository")
    def test_description_set_when_description_update_enabled(self, mock_tracking_cls):
        """Given description_update=True, request.description is populated."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=True, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.description is not None
        assert req.title is None

    @patch("services.mr_service.TrackingRepository")
    def test_description_not_set_when_description_update_disabled(self, mock_tracking_cls):
        """Given description_update=False, request.description is None."""
        service, git_repo, glab_repo, _ = _make_service(title_update=True, description_update=False, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.description is None

    # --- Labeling flag ---

    @patch("services.mr_service.TrackingRepository")
    def test_label_to_add_set_when_no_prior_ai_label_and_labeling_enabled(self, mock_tracking_cls):
        """Given labeling=True and no existing AI label, request.label_to_add is set."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=False, labeling_enabled=True)
        tracking = self._setup(service, git_repo, glab_repo, existing_labels=[], ai_pct=85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.label_to_add == "AI:85%"
        assert req.label_to_remove is None

    @patch("services.mr_service.TrackingRepository")
    def test_label_replace_when_percentage_changed(self, mock_tracking_cls):
        """Given labeling=True and stale AI label, request has remove+add."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=False, labeling_enabled=True)
        tracking = self._setup(service, git_repo, glab_repo, existing_labels=["AI:70%"], ai_pct=85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.label_to_remove == "AI:70%"
        assert req.label_to_add == "AI:85%"

    @patch("services.mr_service.TrackingRepository")
    def test_label_unchanged_skipped(self, mock_tracking_cls):
        """Given labeling=True and label already correct, no label fields in request."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=False, labeling_enabled=True)
        tracking = self._setup(service, git_repo, glab_repo, existing_labels=["AI:85%"], ai_pct=85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        # Empty request → update_mr not called
        service.process_push()

        glab_repo.update_mr.assert_not_called()

    @patch("services.mr_service.TrackingRepository")
    def test_label_not_set_when_labeling_disabled(self, mock_tracking_cls):
        """Given labeling=False, no label fields in request."""
        service, git_repo, glab_repo, _ = _make_service(title_update=True, description_update=False, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.label_to_add is None
        assert req.label_to_remove is None

    # --- All flags on ---

    @patch("services.mr_service.TrackingRepository")
    def test_all_flags_enabled_populates_all_fields(self, mock_tracking_cls):
        """Given T+D+L all enabled, request has title, description, and label."""
        service, git_repo, glab_repo, _ = _make_service(title_update=True, description_update=True, labeling_enabled=True)
        tracking = self._setup(service, git_repo, glab_repo, existing_labels=[], ai_pct=85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        req = self._get_update_request(glab_repo)
        assert req.title is not None
        assert req.description is not None
        assert req.label_to_add == "AI:85%"

    # --- No flags → no call ---

    @patch("services.mr_service.TrackingRepository")
    def test_no_flags_enabled_no_update_call(self, mock_tracking_cls):
        """Given all flags off, update_mr is never called."""
        service, git_repo, glab_repo, _ = _make_service(title_update=False, description_update=False, labeling_enabled=False)
        tracking = self._setup(service, git_repo, glab_repo)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        glab_repo.update_mr.assert_not_called()

    # --- Single call guarantee ---

    @patch("services.mr_service.TrackingRepository")
    def test_update_mr_called_exactly_once(self, mock_tracking_cls):
        """Given any active flags, update_mr is called at most once per push."""
        service, git_repo, glab_repo, _ = _make_service(title_update=True, description_update=True, labeling_enabled=True)
        tracking = self._setup(service, git_repo, glab_repo, existing_labels=["AI:70%"], ai_pct=85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service.process_push()

        assert glab_repo.update_mr.call_count == 1


class TestAutoCreateMrFlagIndependence:
    """Tests verifying T/D/L flags are independent in _auto_create_mr."""

    def _setup(self, service, git_repo, glab_repo, ai_pct=85.0):
        """Wire up mocks for _auto_create_mr."""
        git_repo.resolve_target_branch.return_value = "main"
        git_repo.get_root.return_value = Path("/fake/root")
        glab_repo.create_draft_mr.return_value = True
        return _make_tracking_mock(ai_pct)

    def _create_call(self, glab_repo):
        """Return (title, description, label) from create_draft_mr call args."""
        args = glab_repo.create_draft_mr.call_args
        title = args[0][1] if len(args[0]) >= 2 else args.kwargs.get('title')
        description = args[0][3] if len(args[0]) >= 4 else args.kwargs.get('description', '')
        label = args.kwargs.get('label') or (args[0][4] if len(args[0]) >= 5 else None)
        return title, description, label

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_title_has_ai_tag_when_title_update_enabled(self, mock_tracking_cls, mock_git_cls):
        """Given T=True, MR title includes the AI stats tag."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=True, description_update=False, labeling_enabled=False, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        title, description, label = self._create_call(glab_repo)
        assert "[AI:" in title
        assert description == ''
        assert label is None

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_title_has_no_ai_tag_when_title_update_disabled(self, mock_tracking_cls, mock_git_cls):
        """Given T=False, MR title has no AI stats tag."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=False, description_update=False, labeling_enabled=False, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        title, _, _ = self._create_call(glab_repo)
        assert "[AI:" not in title

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_description_has_stats_when_description_update_enabled(self, mock_tracking_cls, mock_git_cls):
        """Given D=True, MR description contains AI stats section."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=False, description_update=True, labeling_enabled=False, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        _, description, _ = self._create_call(glab_repo)
        assert "AI Contribution Stats" in description

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_description_empty_when_description_update_disabled(self, mock_tracking_cls, mock_git_cls):
        """Given D=False, MR description is empty."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=False, description_update=False, labeling_enabled=False, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        _, description, _ = self._create_call(glab_repo)
        assert description == ''

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_label_set_when_labeling_enabled(self, mock_tracking_cls, mock_git_cls):
        """Given L=True, create_draft_mr called with AI label."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=False, description_update=False, labeling_enabled=True, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        _, _, label = self._create_call(glab_repo)
        assert label == "AI:85%"

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_label_none_when_labeling_disabled(self, mock_tracking_cls, mock_git_cls):
        """Given L=False, create_draft_mr called without label."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=False, description_update=False, labeling_enabled=False, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        _, _, label = self._create_call(glab_repo)
        assert label is None

    @patch("services.mr_service.GitRepository")
    @patch("services.mr_service.TrackingRepository")
    def test_all_flags_enabled_populates_all_content(self, mock_tracking_cls, mock_git_cls):
        """Given T+D+L all enabled, MR gets title tag, description stats, and label."""
        service, git_repo, glab_repo, _ = _make_service(
            title_update=True, description_update=True, labeling_enabled=True, auto_creation=True
        )
        tracking = self._setup(service, git_repo, glab_repo, 85.0)
        mock_tracking_cls.return_value.load.return_value = tracking

        service._auto_create_mr("feature/PROJ-1-test")

        title, description, label = self._create_call(glab_repo)
        assert "[AI:" in title
        assert "AI Contribution Stats" in description
        assert label == "AI:85%"
