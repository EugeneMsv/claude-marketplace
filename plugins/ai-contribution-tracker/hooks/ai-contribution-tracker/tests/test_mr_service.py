"""Tests for MrService."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.contribution_stats import (
    ContributionStats,
    ContributorStats,
    LineStats,
)
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
