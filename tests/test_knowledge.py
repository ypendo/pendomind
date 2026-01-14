"""Tests for PendoMind knowledge base module (Qdrant wrapper)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestKnowledgeBaseInit:
    """Test knowledge base initialization."""

    def test_creates_collection_if_not_exists(self):
        """Should create Qdrant collection on init if it doesn't exist."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = False
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)

            mock_client.create_collection.assert_called_once()

    def test_skips_collection_creation_if_exists(self):
        """Should skip collection creation if it already exists."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)

            mock_client.create_collection.assert_not_called()

    def test_uses_config_collection_name(self):
        """Should use collection name from config."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            config.qdrant.collection_name = "custom_collection"
            kb = KnowledgeBase(config)

            mock_client.collection_exists.assert_called_with("custom_collection")


class TestKnowledgeBaseStore:
    """Test storing knowledge entries."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_store_generates_deterministic_id(self, mock_kb):
        """Same content+source should generate same ID (for idempotent upserts)."""
        kb, mock_client = mock_kb

        id1 = await kb.store(
            content="Test bug fix content",
            type="bug",
            tags=["test"],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
        )

        id2 = await kb.store(
            content="Test bug fix content",
            type="bug",
            tags=["test"],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
        )

        assert id1 == id2

    @pytest.mark.asyncio
    async def test_store_different_content_different_id(self, mock_kb):
        """Different content should get different IDs."""
        kb, mock_client = mock_kb

        id1 = await kb.store(
            content="First content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
        )

        id2 = await kb.store(
            content="Different content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.2] * 1536,
        )

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_store_upserts_to_qdrant(self, mock_kb):
        """Store should upsert point to Qdrant."""
        kb, mock_client = mock_kb

        await kb.store(
            content="Test content",
            type="bug",
            tags=["test"],
            source="github",
            file_paths=["src/api.py"],
            embedding=[0.1] * 1536,
        )

        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        assert call_args[1]["collection_name"] == "pendomind_knowledge"

    @pytest.mark.asyncio
    async def test_store_includes_all_payload_fields(self, mock_kb):
        """Stored payload should include all metadata fields."""
        kb, mock_client = mock_kb

        await kb.store(
            content="Test content for storage",
            type="feature",
            tags=["tag1", "tag2"],
            source="confluence",
            file_paths=["src/main.py", "src/utils.py"],
            embedding=[0.1] * 1536,
        )

        call_args = mock_client.upsert.call_args
        points = call_args[1]["points"]
        payload = points[0].payload

        assert payload["content"] == "Test content for storage"
        assert payload["type"] == "feature"
        assert payload["tags"] == ["tag1", "tag2"]
        assert payload["source"] == "confluence"
        assert payload["file_paths"] == ["src/main.py", "src/utils.py"]
        assert "created_at" in payload

    @pytest.mark.asyncio
    async def test_store_returns_point_id(self, mock_kb):
        """Store should return the generated point ID."""
        kb, mock_client = mock_kb

        point_id = await kb.store(
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
        )

        assert point_id is not None
        assert len(point_id) > 0


class TestKnowledgeBaseSearch:
    """Test searching knowledge entries."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_kb):
        """Search should return formatted results from Qdrant."""
        kb, mock_client = mock_kb

        # qdrant-client 1.9+ uses query_points returning QueryResponse with .points
        mock_client.query_points.return_value = MagicMock(
            points=[
                MagicMock(
                    id="result-1",
                    score=0.95,
                    payload={
                        "content": "Bug fix content",
                        "type": "bug",
                        "tags": ["test"],
                        "source": "github",
                    },
                )
            ]
        )

        results = await kb.search([0.1] * 1536)

        assert len(results) == 1
        assert results[0]["id"] == "result-1"
        assert results[0]["score"] == 0.95
        assert results[0]["content"] == "Bug fix content"

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, mock_kb):
        """Search should apply type filter when provided."""
        kb, mock_client = mock_kb
        mock_client.query_points.return_value = MagicMock(points=[])

        await kb.search([0.1] * 1536, type_filter="incident")

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, mock_kb):
        """Search should respect the limit parameter."""
        kb, mock_client = mock_kb
        mock_client.query_points.return_value = MagicMock(points=[])

        await kb.search([0.1] * 1536, limit=5)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_search_default_limit(self, mock_kb):
        """Search should use default limit of 10."""
        kb, mock_client = mock_kb
        mock_client.query_points.return_value = MagicMock(points=[])

        await kb.search([0.1] * 1536)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["limit"] == 10


class TestKnowledgeBaseDuplicates:
    """Test duplicate detection."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_find_duplicates_returns_similar_items(self, mock_kb):
        """find_duplicates should return items above similarity threshold."""
        kb, mock_client = mock_kb

        # qdrant-client 1.9+ uses query_points returning QueryResponse with .points
        mock_client.query_points.return_value = MagicMock(
            points=[
                MagicMock(
                    id="dup-1",
                    score=0.95,
                    payload={"content": "Very similar content", "type": "bug"},
                ),
                MagicMock(
                    id="dup-2",
                    score=0.85,  # Below 0.90 threshold
                    payload={"content": "Somewhat similar", "type": "bug"},
                ),
            ]
        )

        duplicates = await kb.find_duplicates([0.1] * 1536, threshold=0.90)

        # Should only return items above threshold
        assert len(duplicates) == 1
        assert duplicates[0]["id"] == "dup-1"
        assert duplicates[0]["similarity_score"] == 0.95

    @pytest.mark.asyncio
    async def test_find_duplicates_empty_when_none_similar(self, mock_kb):
        """find_duplicates should return empty list when no similar items."""
        kb, mock_client = mock_kb

        mock_client.query_points.return_value = MagicMock(
            points=[
                MagicMock(
                    id="not-dup",
                    score=0.50,  # Well below threshold
                    payload={"content": "Different content", "type": "bug"},
                ),
            ]
        )

        duplicates = await kb.find_duplicates([0.1] * 1536, threshold=0.90)

        assert len(duplicates) == 0

    @pytest.mark.asyncio
    async def test_find_duplicates_uses_config_threshold(self, mock_kb):
        """find_duplicates should use threshold from config if not specified."""
        kb, mock_client = mock_kb
        kb.config.thresholds.duplicate_similarity = 0.85

        mock_client.query_points.return_value = MagicMock(
            points=[
                MagicMock(
                    id="dup-1",
                    score=0.87,
                    payload={"content": "Similar content", "type": "bug"},
                ),
            ]
        )

        # Don't specify threshold - should use config value
        duplicates = await kb.find_duplicates([0.1] * 1536)

        assert len(duplicates) == 1


class TestKnowledgeBaseFileContext:
    """Test file path based retrieval."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_get_by_file_path_returns_related(self, mock_kb):
        """get_by_file_path should return knowledge related to a file."""
        kb, mock_client = mock_kb

        mock_client.scroll.return_value = (
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
            None,  # No next page
        )

        results = await kb.get_by_file_path("src/api.py")

        assert len(results) == 1
        assert results[0]["content"] == "Bug fix in api.py"

    @pytest.mark.asyncio
    async def test_get_by_file_path_filters_correctly(self, mock_kb):
        """get_by_file_path should apply correct filter to Qdrant."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        await kb.get_by_file_path("src/utils.py")

        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["scroll_filter"] is not None

    @pytest.mark.asyncio
    async def test_get_by_file_path_empty_when_no_match(self, mock_kb):
        """get_by_file_path should return empty list when no matches."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        results = await kb.get_by_file_path("nonexistent/file.py")

        assert len(results) == 0


class TestKnowledgeBaseEmbedding:
    """Test embedding generation using FastEmbed (runs locally)."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked dependencies."""
        import numpy as np

        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            # FastEmbed's embed() returns a generator of numpy arrays
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            kb._embedder = mock_embedder
            yield kb, mock_embedder

    @pytest.mark.asyncio
    async def test_get_embedding_calls_fastembed(self, mock_kb):
        """get_embedding should call FastEmbed's embed method (runs locally)."""
        import numpy as np

        kb, mock_embedder = mock_kb

        # Reset mock to provide fresh generator
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])

        embedding = await kb.get_embedding("Test content for embedding")

        mock_embedder.embed.assert_called_once_with(["Test content for embedding"])
        assert len(embedding) == 384  # bge-small-en-v1.5 produces 384 dimensions

    @pytest.mark.asyncio
    async def test_get_embedding_returns_list(self, mock_kb):
        """get_embedding should return a Python list (not numpy array)."""
        import numpy as np

        kb, mock_embedder = mock_kb
        mock_embedder.embed.return_value = iter([np.array([0.5] * 384)])

        embedding = await kb.get_embedding("Test content")

        assert isinstance(embedding, list)
        assert all(isinstance(x, float) for x in embedding)


class TestKnowledgeBaseGetAll:
    """Test listing all knowledge entries."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_get_all_returns_all_entries(self, mock_kb):
        """get_all should return all entries from Qdrant."""
        kb, mock_client = mock_kb

        mock_client.scroll.return_value = (
            [
                MagicMock(
                    id="entry-1",
                    payload={
                        "content": "Bug fix content",
                        "type": "bug",
                        "tags": ["test"],
                    },
                ),
                MagicMock(
                    id="entry-2",
                    payload={
                        "content": "Feature content",
                        "type": "feature",
                        "tags": ["new"],
                    },
                ),
            ],
            None,  # No next page
        )

        results = await kb.get_all()

        assert len(results) == 2
        assert results[0]["id"] == "entry-1"
        assert results[0]["type"] == "bug"
        assert results[1]["id"] == "entry-2"
        assert results[1]["type"] == "feature"

    @pytest.mark.asyncio
    async def test_get_all_with_type_filter(self, mock_kb):
        """get_all should apply type filter when provided."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        await kb.get_all(type_filter="incident")

        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["scroll_filter"] is not None

    @pytest.mark.asyncio
    async def test_get_all_respects_limit(self, mock_kb):
        """get_all should respect the limit parameter."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        await kb.get_all(limit=50)

        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_all_empty_collection(self, mock_kb):
        """get_all should return empty list for empty collection."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        results = await kb.get_all()

        assert results == []

    @pytest.mark.asyncio
    async def test_get_all_without_filter(self, mock_kb):
        """get_all without filter should not apply scroll_filter."""
        kb, mock_client = mock_kb
        mock_client.scroll.return_value = ([], None)

        await kb.get_all()

        call_kwargs = mock_client.scroll.call_args[1]
        assert call_kwargs["scroll_filter"] is None


class TestKnowledgeBaseDelete:
    """Test deleting knowledge entries."""

    @pytest.fixture
    def mock_kb(self):
        """Create KB with mocked Qdrant client."""
        with patch("pendomind.knowledge.QdrantClient") as mock_qdrant, \
             patch("pendomind.knowledge.TextEmbedding"):
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_qdrant.return_value = mock_client

            from pendomind.knowledge import KnowledgeBase
            from pendomind.config import PendoMindConfig

            config = PendoMindConfig()
            kb = KnowledgeBase(config)
            kb._client = mock_client
            yield kb, mock_client

    @pytest.mark.asyncio
    async def test_delete_by_id(self, mock_kb):
        """delete should remove entry by ID."""
        kb, mock_client = mock_kb

        await kb.delete("entry-123")

        mock_client.delete.assert_called_once()
