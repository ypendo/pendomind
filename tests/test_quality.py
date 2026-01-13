"""Tests for PendoMind quality scoring module."""

import pytest


class TestRelevanceScoring:
    """Test relevance score calculation (40% of composite)."""

    @pytest.fixture
    def scorer(self):
        from pendomind.quality import QualityScorer

        return QualityScorer()

    @pytest.mark.asyncio
    async def test_high_relevance_bug_with_stack_trace(self, scorer):
        """Bug report with stack trace should score >= 0.7 relevance."""
        content = """
        Bug: NullPointerException in UserService

        Stack trace:
        Traceback (most recent call last):
            File "user_service.py", line 42, in get_user
                return user.name
        AttributeError: 'NoneType' object has no attribute 'name'

        Fix: Added null check before accessing user.name
        """
        score, _ = await scorer.calculate_relevance(content, "bug")

        assert score >= 0.7, f"Bug with stack trace should have high relevance, got {score}"

    @pytest.mark.asyncio
    async def test_low_relevance_generic_text(self, scorer):
        """Non-technical text should score < 0.3 relevance."""
        content = "Had a meeting today about the project timeline."
        score, _ = await scorer.calculate_relevance(content, "feature")

        assert score < 0.3, f"Non-technical content should have low relevance, got {score}"

    @pytest.mark.asyncio
    async def test_code_block_increases_relevance(self, scorer):
        """Content with code blocks should score higher than without."""
        without_code = "Fixed the user authentication issue"
        with_code = """
        Fixed the user authentication issue
        ```python
        def authenticate(user):
            return verify_token(user.token)
        ```
        """
        score_without, _ = await scorer.calculate_relevance(without_code, "bug")
        score_with, _ = await scorer.calculate_relevance(with_code, "bug")

        assert score_with > score_without, "Code blocks should increase relevance"

    @pytest.mark.asyncio
    async def test_incident_type_bonus_for_rca(self, scorer):
        """Incident with RCA keywords should get type bonus."""
        with_rca = "Root cause analysis: The service crashed due to memory leak. RCA shows connection pool exhaustion."
        without_rca = "The service crashed due to some issue"

        score_with, _ = await scorer.calculate_relevance(with_rca, "incident")
        score_without, _ = await scorer.calculate_relevance(without_rca, "incident")

        assert score_with > score_without, "RCA keywords should increase incident relevance"

    @pytest.mark.asyncio
    async def test_error_pattern_detection(self, scorer):
        """Content with error patterns should have higher relevance."""
        with_error = "Error: Connection refused. Exception thrown at line 42."
        without_error = "The connection didn't work properly"

        score_with, _ = await scorer.calculate_relevance(with_error, "error")
        score_without, _ = await scorer.calculate_relevance(without_error, "error")

        assert score_with > score_without, "Error patterns should increase relevance"


class TestCompletenessScoring:
    """Test completeness score calculation (35% of composite)."""

    @pytest.fixture
    def scorer(self):
        from pendomind.quality import QualityScorer

        return QualityScorer()

    @pytest.mark.asyncio
    async def test_complete_bug_report_scores_high(self, scorer):
        """Bug report with all sections should score >= 0.8."""
        content = """
        Problem: Users unable to log in after password reset

        Context: This affects version 2.1.0 in production

        Root Cause: The password hash was not being updated correctly

        Solution: Fixed the hash update in PasswordService.reset()

        Steps to reproduce:
        1. Request password reset
        2. Set new password
        3. Try to log in
        """
        score, _ = await scorer.calculate_completeness(content, "bug")

        assert score >= 0.8, f"Complete bug report should score high, got {score}"

    @pytest.mark.asyncio
    async def test_very_short_content_penalized(self, scorer):
        """Content < 20 words should score very low (< 0.25)."""
        content = "Did something"
        score, _ = await scorer.calculate_completeness(content, "bug")

        assert score < 0.15, f"Very short content without keywords should score very low, got {score}"

    @pytest.mark.asyncio
    async def test_missing_solution_reduces_score(self, scorer):
        """Content missing solution section should have lower score."""
        with_solution = """
        Problem: Login fails.
        Cause: Token expired.
        Solution: Refresh token before each request.
        """
        without_solution = """
        Problem: Login fails.
        The issue seems to be related to tokens somehow.
        """

        score_with, _ = await scorer.calculate_completeness(with_solution, "bug")
        score_without, _ = await scorer.calculate_completeness(without_solution, "bug")

        assert score_with > score_without, "Missing solution should reduce score"

    @pytest.mark.asyncio
    async def test_actionable_steps_increase_score(self, scorer):
        """Content with actionable steps should score higher."""
        without_steps = "Fixed the database connection issue by changing settings"
        with_steps = """
        Fixed the database connection issue:
        1. First, check the connection pool settings
        2. Then, increase max_connections to 50
        3. Finally, restart the service
        Run this command to verify: `docker ps`
        """

        score_without, _ = await scorer.calculate_completeness(without_steps, "bug")
        score_with, _ = await scorer.calculate_completeness(with_steps, "bug")

        assert score_with > score_without, "Actionable steps should increase score"

    @pytest.mark.asyncio
    async def test_moderate_length_content(self, scorer):
        """Content with 50-150 words should score moderately."""
        content = " ".join(["word"] * 100)  # 100 words
        score, details = await scorer.calculate_completeness(content, "bug")

        # Should get length points but lack structure
        assert 0.15 <= score <= 0.4, f"Moderate length content should score moderately, got {score}"


class TestCredibilityScoring:
    """Test credibility score calculation (25% of composite)."""

    @pytest.fixture
    def scorer(self):
        from pendomind.quality import QualityScorer

        return QualityScorer()

    @pytest.mark.asyncio
    async def test_github_source_highest_credibility(self, scorer):
        """GitHub source should score 0.95."""
        score, explanation = await scorer.calculate_credibility("github")

        assert score == 0.95
        assert "github" in explanation.lower()

    @pytest.mark.asyncio
    async def test_confluence_source_credibility(self, scorer):
        """Confluence source should score 0.85."""
        score, _ = await scorer.calculate_credibility("confluence")

        assert score == 0.85

    @pytest.mark.asyncio
    async def test_jira_source_credibility(self, scorer):
        """Jira source should score 0.80."""
        score, _ = await scorer.calculate_credibility("jira")

        assert score == 0.80

    @pytest.mark.asyncio
    async def test_claude_session_credibility(self, scorer):
        """Claude session source should score 0.70."""
        score, _ = await scorer.calculate_credibility("claude_session")

        assert score == 0.70

    @pytest.mark.asyncio
    async def test_slack_source_lower_credibility(self, scorer):
        """Slack source should score 0.60."""
        score, _ = await scorer.calculate_credibility("slack")

        assert score == 0.60

    @pytest.mark.asyncio
    async def test_unknown_source_default_credibility(self, scorer):
        """Unknown source should score 0.50 (default)."""
        score, _ = await scorer.calculate_credibility("unknown_source")

        assert score == 0.50


class TestCompositeScoring:
    """Test composite score calculation."""

    @pytest.fixture
    def scorer(self):
        from pendomind.quality import QualityScorer

        return QualityScorer()

    @pytest.mark.asyncio
    async def test_composite_uses_correct_weights(self, scorer):
        """Verify composite = 0.4*rel + 0.35*comp + 0.25*cred."""
        content = """
        Bug: Database connection timeout
        Problem: Connections timing out after 30 seconds
        Cause: Connection pool exhausted
        Solution: Increased pool size from 10 to 50
        ```python
        pool_size = 50
        ```
        """
        analysis = await scorer.score(content, "bug", "github")

        expected = (
            analysis.relevance_score * 0.40
            + analysis.completeness_score * 0.35
            + analysis.credibility_score * 0.25
        )

        assert abs(analysis.composite_score - expected) < 0.01

    @pytest.mark.asyncio
    async def test_low_quality_generates_recommendations(self, scorer):
        """Low-quality content should have recommendations."""
        content = "Fixed something"
        analysis = await scorer.score(content, "bug", "slack")

        assert len(analysis.recommendations) > 0

    @pytest.mark.asyncio
    async def test_high_quality_content_scores_above_threshold(
        self, scorer, sample_bug_content
    ):
        """High-quality content should score >= 0.65 (storage threshold)."""
        analysis = await scorer.score(sample_bug_content, "bug", "github")

        assert analysis.composite_score >= 0.65

    @pytest.mark.asyncio
    async def test_low_quality_content_scores_below_threshold(
        self, scorer, sample_low_quality_content
    ):
        """Low-quality content should score < 0.65."""
        analysis = await scorer.score(sample_low_quality_content, "bug", "slack")

        assert analysis.composite_score < 0.65

    @pytest.mark.asyncio
    async def test_analysis_contains_all_fields(self, scorer):
        """QualityAnalysis should have all required fields."""
        content = "Test content for analysis"
        analysis = await scorer.score(content, "bug", "github")

        assert hasattr(analysis, "relevance_score")
        assert hasattr(analysis, "completeness_score")
        assert hasattr(analysis, "credibility_score")
        assert hasattr(analysis, "composite_score")
        assert hasattr(analysis, "relevance_details")
        assert hasattr(analysis, "completeness_details")
        assert hasattr(analysis, "recommendations")

    @pytest.mark.asyncio
    async def test_scores_are_normalized_0_to_1(self, scorer, sample_bug_content):
        """All scores should be between 0 and 1."""
        analysis = await scorer.score(sample_bug_content, "bug", "github")

        assert 0 <= analysis.relevance_score <= 1
        assert 0 <= analysis.completeness_score <= 1
        assert 0 <= analysis.credibility_score <= 1
        assert 0 <= analysis.composite_score <= 1


class TestQualityAnalysisModel:
    """Test QualityAnalysis data model."""

    def test_quality_analysis_creation(self):
        """QualityAnalysis can be created with all fields."""
        from pendomind.quality import QualityAnalysis

        analysis = QualityAnalysis(
            relevance_score=0.8,
            completeness_score=0.7,
            credibility_score=0.9,
            composite_score=0.78,
            relevance_details="Good technical content",
            completeness_details="Has problem and solution",
            recommendations=["Consider adding more context"],
        )

        assert analysis.relevance_score == 0.8
        assert analysis.composite_score == 0.78
        assert len(analysis.recommendations) == 1
