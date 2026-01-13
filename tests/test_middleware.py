"""Tests for PendoMind quality control middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestQualityMiddlewareValidation:
    """Test content validation in middleware."""

    @pytest.fixture
    def middleware(self):
        from pendomind.middleware import QualityMiddleware
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        return QualityMiddleware(config)

    def test_validate_type_valid(self, middleware):
        """Valid type should pass validation."""
        result = middleware.validate_type("bug")

        assert result.is_valid is True
        assert result.error is None

    def test_validate_type_invalid(self, middleware):
        """Invalid type should fail validation."""
        result = middleware.validate_type("invalid_type")

        assert result.is_valid is False
        assert "Invalid type" in result.error

    def test_validate_type_all_allowed_types(self, middleware):
        """All configured types should pass validation."""
        for type_name in ["bug", "feature", "incident", "debugging", "architecture", "error"]:
            result = middleware.validate_type(type_name)
            assert result.is_valid is True, f"Type '{type_name}' should be valid"

    def test_validate_content_no_excluded_patterns(self, middleware):
        """Content without excluded patterns should pass."""
        content = "Fixed the database connection timeout issue by increasing pool size."
        result = middleware.validate_content(content)

        assert result.is_valid is True

    def test_validate_content_rejects_password(self, middleware):
        """Content with 'password' should be rejected."""
        content = "Set the password to secret123 in the config."
        result = middleware.validate_content(content)

        assert result.is_valid is False
        assert "excluded pattern" in result.error.lower()

    def test_validate_content_rejects_api_key(self, middleware):
        """Content with 'api_key' should be rejected."""
        content = "The api_key for production is abc123xyz."
        result = middleware.validate_content(content)

        assert result.is_valid is False

    def test_validate_content_rejects_secret(self, middleware):
        """Content with 'secret' should be rejected."""
        content = "Store the client_secret in environment variables."
        result = middleware.validate_content(content)

        assert result.is_valid is False

    def test_validate_content_rejects_token(self, middleware):
        """Content with 'token' should be rejected."""
        content = "The auth token expires after 24 hours."
        result = middleware.validate_content(content)

        assert result.is_valid is False

    def test_validate_content_rejects_private_key(self, middleware):
        """Content with 'private_key' should be rejected."""
        content = "Generate a new private_key for SSL certificates."
        result = middleware.validate_content(content)

        assert result.is_valid is False

    def test_validate_length_too_short(self, middleware):
        """Content below minimum length should fail."""
        content = "Fixed bug"  # Too short
        result = middleware.validate_length(content)

        assert result.is_valid is False
        assert "too short" in result.error.lower()

    def test_validate_length_valid(self, middleware):
        """Content within length limits should pass."""
        content = "Fixed the user authentication bug by checking token expiry before making API calls. This ensures that expired tokens are refreshed automatically when needed."
        result = middleware.validate_length(content)

        assert result.is_valid is True

    def test_validate_length_too_long(self, middleware):
        """Content above maximum length should fail."""
        content = "word " * 6000  # Way over 5000 word limit
        result = middleware.validate_length(content)

        assert result.is_valid is False
        assert "too long" in result.error.lower()


class TestQualityMiddlewareProcessing:
    """Test the full middleware processing flow."""

    @pytest.fixture
    def middleware(self):
        from pendomind.middleware import QualityMiddleware
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        return QualityMiddleware(config)

    @pytest.fixture
    def mock_scorer(self):
        """Mock quality scorer."""
        from pendomind.quality import QualityAnalysis

        mock = MagicMock()
        mock.score = AsyncMock(
            return_value=QualityAnalysis(
                relevance_score=0.8,
                completeness_score=0.7,
                credibility_score=0.9,
                composite_score=0.80,
                relevance_details="Good",
                completeness_details="Good",
                recommendations=[],
            )
        )
        return mock

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock = MagicMock()
        mock.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        mock.find_duplicates = AsyncMock(return_value=[])
        mock.store = AsyncMock(return_value="stored-123")
        return mock

    @pytest.fixture
    def mock_pending_store(self):
        """Mock pending store."""
        mock = MagicMock()
        mock.add = MagicMock(return_value="pending-456")
        return mock

    @pytest.mark.asyncio
    async def test_process_rejects_invalid_type(self, middleware):
        """Invalid type should be rejected immediately."""
        result = await middleware.process(
            content="Valid content that is long enough to pass length check",
            type="invalid",
            tags=[],
            source="github",
            file_paths=None,
        )

        assert result["status"] == "rejected"
        assert "Invalid type" in result["message"]

    @pytest.mark.asyncio
    async def test_process_rejects_excluded_pattern(self, middleware):
        """Content with excluded pattern should be rejected."""
        result = await middleware.process(
            content="Set the password to secret123 in the config file for production access.",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
        )

        assert result["status"] == "rejected"
        assert "excluded pattern" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_process_rejects_too_short(self, middleware):
        """Too short content should be rejected."""
        result = await middleware.process(
            content="Fixed bug",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
        )

        assert result["status"] == "rejected"
        assert "too short" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_process_auto_rejects_low_quality(
        self, middleware, mock_scorer, mock_kb
    ):
        """Low quality content should be auto-rejected."""
        from pendomind.quality import QualityAnalysis

        mock_scorer.score = AsyncMock(
            return_value=QualityAnalysis(
                relevance_score=0.3,
                completeness_score=0.2,
                credibility_score=0.5,
                composite_score=0.30,  # Below 0.65 threshold
                relevance_details="Low",
                completeness_details="Low",
                recommendations=["Add more detail"],
            )
        )

        middleware.scorer = mock_scorer
        middleware.kb = mock_kb

        result = await middleware.process(
            content="This content is valid length but low quality and lacks technical depth. It does not contain enough information to be useful for future reference or debugging purposes.",
            type="bug",
            tags=[],
            source="slack",
            file_paths=None,
        )

        assert result["status"] == "rejected"
        assert result["quality_score"] < 0.65

    @pytest.mark.asyncio
    async def test_process_auto_approves_high_quality(
        self, middleware, mock_scorer, mock_kb
    ):
        """High quality content should be auto-stored."""
        from pendomind.quality import QualityAnalysis

        mock_scorer.score = AsyncMock(
            return_value=QualityAnalysis(
                relevance_score=0.9,
                completeness_score=0.9,
                credibility_score=0.95,
                composite_score=0.91,  # Above 0.85 threshold
                relevance_details="Excellent",
                completeness_details="Complete",
                recommendations=[],
            )
        )

        middleware.scorer = mock_scorer
        middleware.kb = mock_kb

        result = await middleware.process(
            content="""
            Bug: Database connection timeout after upgrade.
            Problem: Users seeing 500 errors on login page.
            Root Cause: Connection pool size was too small for new traffic.
            Solution: Increased pool from 10 to 50 connections.
            ```python
            pool_size = 50
            ```
            Verified fix in production - error rate dropped to 0%.
            """,
            type="bug",
            tags=["database", "production"],
            source="github",
            file_paths=["src/db.py"],
        )

        assert result["status"] == "stored"
        mock_kb.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_returns_pending_for_medium_quality(
        self, middleware, mock_scorer, mock_kb, mock_pending_store
    ):
        """Medium quality content should go to pending."""
        from pendomind.quality import QualityAnalysis

        mock_scorer.score = AsyncMock(
            return_value=QualityAnalysis(
                relevance_score=0.7,
                completeness_score=0.7,
                credibility_score=0.8,
                composite_score=0.72,  # Between 0.65 and 0.85
                relevance_details="Good",
                completeness_details="Adequate",
                recommendations=["Add more context"],
            )
        )

        middleware.scorer = mock_scorer
        middleware.kb = mock_kb
        middleware.pending_store = mock_pending_store

        result = await middleware.process(
            content="Fixed the authentication issue by checking session validity before API calls. The issue was caused by stale sessions not being detected properly, leading to failed API requests in production.",
            type="bug",
            tags=["auth"],
            source="confluence",
            file_paths=None,
        )

        assert result["status"] == "pending"
        assert result["pending_id"] is not None
        mock_pending_store.add.assert_called_once()


class TestQualityMiddlewareDuplicateDetection:
    """Test duplicate detection in middleware."""

    @pytest.fixture
    def middleware(self):
        from pendomind.middleware import QualityMiddleware
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        return QualityMiddleware(config)

    @pytest.fixture
    def mock_scorer(self):
        from pendomind.quality import QualityAnalysis

        mock = MagicMock()
        mock.score = AsyncMock(
            return_value=QualityAnalysis(
                relevance_score=0.9,
                completeness_score=0.9,
                credibility_score=0.95,
                composite_score=0.91,
                relevance_details="Good",
                completeness_details="Good",
                recommendations=[],
            )
        )
        return mock

    @pytest.fixture
    def mock_kb_with_duplicates(self):
        """Mock KB that returns duplicates."""
        mock = MagicMock()
        mock.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        mock.find_duplicates = AsyncMock(
            return_value=[
                {
                    "id": "existing-123",
                    "similarity_score": 0.95,
                    "content_preview": "Very similar bug fix...",
                    "type": "bug",
                }
            ]
        )
        mock.store = AsyncMock(return_value="stored-456")
        return mock

    @pytest.mark.asyncio
    async def test_process_detects_duplicates(
        self, middleware, mock_scorer, mock_kb_with_duplicates
    ):
        """Should detect and report potential duplicates."""
        middleware.scorer = mock_scorer
        middleware.kb = mock_kb_with_duplicates

        result = await middleware.process(
            content="Fixed the same bug that was fixed before with a similar approach. The database connection pool was exhausted under high load causing timeout errors for users.",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
        )

        # Should still store (high quality) but include duplicate warning
        assert result["status"] == "stored"
        assert "duplicates" in result
        assert len(result["duplicates"]) == 1
        assert result["duplicates"][0]["similarity_score"] == 0.95


class TestValidationResult:
    """Test ValidationResult data class."""

    def test_validation_result_valid(self):
        """Valid result should have is_valid=True and no error."""
        from pendomind.middleware import ValidationResult

        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.error is None

    def test_validation_result_invalid(self):
        """Invalid result should have is_valid=False and error message."""
        from pendomind.middleware import ValidationResult

        result = ValidationResult(is_valid=False, error="Something went wrong")

        assert result.is_valid is False
        assert result.error == "Something went wrong"
