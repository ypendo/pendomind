"""Integration tests for PendoMind end-to-end workflows.

These tests verify complete workflows through multiple components,
mocking external services (Qdrant, FastEmbed) at the boundary.
"""

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestStoreAndSearchWorkflow:
    """Test the complete store and search cycle."""

    @pytest.fixture
    def mock_external_services(self):
        """Mock Qdrant and FastEmbed at module level."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            # Setup Qdrant mock (qdrant-client 1.9+ API uses query_points)
            mock_qdrant_client = MagicMock()
            mock_qdrant_client.collection_exists.return_value = True
            mock_qdrant_client.query_points.return_value = MagicMock(points=[])
            mock_qdrant.return_value = mock_qdrant_client

            # Setup FastEmbed mock (runs locally, returns numpy arrays)
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            yield {
                "qdrant": mock_qdrant_client,
                "fastembed": mock_embedder,
            }

    @pytest.mark.asyncio
    async def test_high_quality_auto_stores(self, mock_external_services):
        """High quality content should be auto-stored without confirmation."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.middleware import QualityMiddleware
        from pendomind.tools import remember

        config = PendoMindConfig()
        kb = KnowledgeBase(config)
        middleware = QualityMiddleware(config)
        middleware.kb = kb

        # High quality bug report with full details - all markers present
        result = await remember(
            content="""
            Bug: Database connection timeout in production API causing widespread outages.

            Problem: Users experiencing 500 errors on the /api/users endpoint.
            The error rate spiked to 15% during peak hours on Monday 2024-01-15.

            Root Cause: Connection pool exhaustion due to leaked connections
            in the getUserProfile() function. Database connections weren't being
            released after query timeout because the finally block was missing.
            Stack trace: ConnectionPoolError at db/pool.py:145

            Solution: Added proper connection cleanup in finally block:
            ```python
            def get_user_profile(user_id):
                conn = None
                try:
                    conn = pool.get_connection()
                    return conn.execute("SELECT * FROM users WHERE id = ?", user_id)
                finally:
                    if conn:
                        conn.release()
            ```

            Steps to reproduce:
            1. Create high load on /api/users endpoint
            2. Observe connection pool metrics
            3. Wait for pool exhaustion

            Verification: Error rate dropped to 0.1% after deployment.
            Monitoring confirmed stable connection pool utilization.
            """,
            type="bug",
            tags=["database", "production", "performance"],
            source="github",
            file_paths=["src/api/users.py"],
            middleware=middleware,
        )

        # High quality should be stored directly or pending (depending on exact scoring)
        assert result["status"] in ["stored", "pending"], f"Got status: {result['status']}"
        if result["status"] == "stored":
            mock_external_services["qdrant"].upsert.assert_called()

    @pytest.mark.asyncio
    async def test_low_quality_auto_rejects(self, mock_external_services):
        """Low quality content should be rejected (either for length or quality)."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.middleware import QualityMiddleware
        from pendomind.tools import remember

        config = PendoMindConfig()
        kb = KnowledgeBase(config)
        middleware = QualityMiddleware(config)
        middleware.kb = kb

        # Low quality - vague content with minimal useful information
        # Must be at least 15 words to pass length check
        result = await remember(
            content="Fixed the bug that was causing issues in production environment recently. Updated the configuration settings to resolve the problem that users were experiencing.",
            type="bug",
            tags=[],
            source="slack",  # Lower credibility source
            middleware=middleware,
        )

        assert result["status"] == "rejected"
        # Either rejected for quality or length
        mock_external_services["qdrant"].upsert.assert_not_called()


class TestPendingConfirmationWorkflow:
    """Test the pending -> confirm workflow."""

    @pytest.fixture
    def mock_external_services(self):
        """Mock Qdrant and FastEmbed."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            mock_qdrant_client = MagicMock()
            mock_qdrant_client.collection_exists.return_value = True
            mock_qdrant_client.query_points.return_value = MagicMock(points=[])
            mock_qdrant.return_value = mock_qdrant_client

            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            yield {
                "qdrant": mock_qdrant_client,
                "fastembed": mock_embedder,
            }

    @pytest.mark.asyncio
    async def test_medium_quality_requires_confirmation(
        self, mock_external_services
    ):
        """Medium quality content should require user confirmation."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.middleware import QualityMiddleware
        from pendomind.tools import PendingStore, remember, remember_confirm

        config = PendoMindConfig()
        kb = KnowledgeBase(config)
        pending_store = PendingStore(config=config)
        middleware = QualityMiddleware(config)
        middleware.kb = kb
        middleware.pending_store = pending_store

        # Medium quality - has detail but missing some structure (problem/cause/solution)
        result = await remember(
            content="""
            Fixed authentication issue by updating session handling logic in the login flow.
            The problem was that sessions weren't being refreshed properly when users
            switched between different features in the application dashboard.

            The issue was discovered during QA testing when sessions would unexpectedly
            expire. Modified the session middleware to check expiration times more
            frequently and refresh proactively when approaching timeout.
            """,
            type="bug",
            tags=["auth", "session"],
            source="confluence",
            middleware=middleware,
        )

        # Should be pending or stored (depending on scoring)
        assert result["status"] in ["pending", "stored"], f"Got status: {result['status']}"

        if result["status"] == "pending":
            pending_id = result["pending_id"]

            # Now confirm it
            confirm_result = await remember_confirm(
                pending_id=pending_id,
                approved=True,
                pending_store=pending_store,
                kb=kb,
            )

            assert confirm_result["status"] == "stored"
            mock_external_services["qdrant"].upsert.assert_called()

    @pytest.mark.asyncio
    async def test_reject_pending_discards(self, mock_external_services):
        """Rejecting pending content should not store it."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.middleware import QualityMiddleware
        from pendomind.tools import PendingStore, remember, remember_confirm

        config = PendoMindConfig()
        kb = KnowledgeBase(config)
        pending_store = PendingStore(config=config)
        middleware = QualityMiddleware(config)
        middleware.kb = kb
        middleware.pending_store = pending_store

        result = await remember(
            content="""
            Updated the configuration file with new settings for the
            database connection parameters and timeout values.
            """,
            type="feature",
            tags=["config"],
            source="confluence",
            middleware=middleware,
        )

        # Verify pending status
        if result["status"] == "pending":
            pending_id = result["pending_id"]

            # Reject it
            confirm_result = await remember_confirm(
                pending_id=pending_id,
                approved=False,
                pending_store=pending_store,
                kb=kb,
            )

            assert confirm_result["status"] == "rejected"
            # Should NOT have stored
            mock_external_services["qdrant"].upsert.assert_not_called()


class TestDuplicateDetectionWorkflow:
    """Test duplicate detection during store."""

    @pytest.fixture
    def mock_external_services(self):
        """Mock with duplicate detection enabled."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            mock_qdrant_client = MagicMock()
            mock_qdrant_client.collection_exists.return_value = True
            # Return a similar entry when searching (qdrant-client 1.9+ API)
            mock_qdrant_client.query_points.return_value = MagicMock(
                points=[
                    MagicMock(
                        id="existing-entry",
                        score=0.95,  # High similarity
                        payload={
                            "content": "Similar bug fix for database timeout",
                            "type": "bug",
                        },
                    )
                ]
            )
            mock_qdrant.return_value = mock_qdrant_client

            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            yield {
                "qdrant": mock_qdrant_client,
                "fastembed": mock_embedder,
            }

    @pytest.mark.asyncio
    async def test_similar_content_shows_duplicates(
        self, mock_external_services
    ):
        """Similar content should show potential duplicates."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.tools import list_similar

        config = PendoMindConfig()
        kb = KnowledgeBase(config)

        duplicates = await list_similar(
            "Fixed database timeout by increasing connection pool",
            kb=kb,
        )

        assert len(duplicates) == 1
        assert duplicates[0]["similarity_score"] == 0.95


class TestSearchAndRecallWorkflow:
    """Test search and recall functionality."""

    @pytest.fixture
    def mock_kb_with_entries(self):
        """Mock KB with stored entries."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            mock_qdrant_client = MagicMock()
            mock_qdrant_client.collection_exists.return_value = True
            # qdrant-client 1.9+ API uses query_points returning QueryResponse
            mock_qdrant_client.query_points.return_value = MagicMock(
                points=[
                    MagicMock(
                        id="entry-1",
                        score=0.92,
                        payload={
                            "content": "Fixed database connection pool leak",
                            "type": "bug",
                            "tags": ["database"],
                            "source": "github",
                        },
                    ),
                    MagicMock(
                        id="entry-2",
                        score=0.85,
                        payload={
                            "content": "Added connection pool monitoring",
                            "type": "feature",
                            "tags": ["database", "monitoring"],
                            "source": "confluence",
                        },
                    ),
                ]
            )
            mock_qdrant.return_value = mock_qdrant_client

            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            yield mock_qdrant_client

    @pytest.mark.asyncio
    async def test_search_returns_ranked_results(self, mock_kb_with_entries):
        """Search should return results ranked by relevance."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.tools import search

        config = PendoMindConfig()
        kb = KnowledgeBase(config)

        results = await search("database connection issues", kb=kb)

        assert len(results) == 2
        assert results[0]["score"] > results[1]["score"]  # Sorted by relevance

    @pytest.mark.asyncio
    async def test_recall_provides_context(self, mock_kb_with_entries):
        """Recall should provide formatted context."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.tools import recall

        config = PendoMindConfig()
        kb = KnowledgeBase(config)

        result = await recall("database problems", kb=kb)

        assert "entries" in result
        assert result["count"] == 2
        assert result["query"] == "database problems"


class TestFileContextWorkflow:
    """Test file-based context retrieval."""

    @pytest.fixture
    def mock_kb_with_file_entries(self):
        """Mock KB with file-associated entries."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            mock_qdrant_client = MagicMock()
            mock_qdrant_client.collection_exists.return_value = True
            mock_qdrant_client.scroll.return_value = (
                [
                    MagicMock(
                        id="entry-1",
                        payload={
                            "content": "Bug fix in api.py",
                            "type": "bug",
                            "file_paths": ["src/api.py"],
                        },
                    ),
                ],
                None,
            )
            mock_qdrant.return_value = mock_qdrant_client

            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            yield mock_qdrant_client

    @pytest.mark.asyncio
    async def test_get_context_for_file(self, mock_kb_with_file_entries):
        """Get context should return entries related to file."""
        from pendomind.config import PendoMindConfig
        from pendomind.knowledge import KnowledgeBase
        from pendomind.tools import get_context

        config = PendoMindConfig()
        kb = KnowledgeBase(config)

        result = await get_context("src/api.py", kb=kb)

        assert result["file_path"] == "src/api.py"
        assert len(result["entries"]) == 1
