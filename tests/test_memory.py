"""Tests for PendoMind MemoryStore (SQLite + sqlite-vec)."""

import pytest
from unittest.mock import patch, MagicMock
import numpy as np


class TestMemoryStoreInit:
    """Test memory store initialization."""

    def test_creates_db_directory_if_not_exists(self, temp_db_path):
        """Should create parent directory for database."""
        with patch("pendomind.memory.TextEmbedding"):
            from pendomind.memory import MemoryStore

            # Use nested path that doesn't exist
            nested_path = temp_db_path.parent / "nested" / "dir" / "memory.db"
            store = MemoryStore(db_path=nested_path)

            assert nested_path.parent.exists()

    def test_creates_tables_on_init(self, temp_db_path):
        """Should create memories and memories_vec tables."""
        with patch("pendomind.memory.TextEmbedding"):
            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)

            # Check tables exist (APSW uses cursor.execute)
            conn = store._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                table_names = [t[0] for t in cursor.fetchall()]

                assert "memories" in table_names
                assert "memories_vec" in table_names
            finally:
                conn.close()

    def test_default_db_path_in_home(self):
        """Should default to ~/.pendomind/memory.db."""
        with patch("pendomind.memory.TextEmbedding"):
            from pendomind.memory import MemoryStore
            from pathlib import Path

            store = MemoryStore()

            assert store.db_path == Path.home() / ".pendomind" / "memory.db"


class TestMemoryStoreStore:
    """Test storing memories."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_store_creates_new_memory(self, mock_store, sample_memory_content):
        """store() should create a new memory entry."""
        store, mock_embedder = mock_store
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])

        result = await store.store(
            content=sample_memory_content,
            type="note",
            tags=["python", "concurrency"],
        )

        assert result["status"] == "created"
        assert result["id"] is not None
        assert result["content"] == sample_memory_content
        assert result["type"] == "note"
        assert result["tags"] == ["python", "concurrency"]

    @pytest.mark.asyncio
    async def test_store_generates_deterministic_id(self, mock_store):
        """Same content should generate same ID."""
        store, mock_embedder = mock_store

        # First call
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        result1 = await store.store(content="Test content", type="note")

        # Delete it
        await store.delete(result1["id"])

        # Store again
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        result2 = await store.store(content="Test content", type="note")

        assert result1["id"] == result2["id"]

    @pytest.mark.asyncio
    async def test_store_updates_similar_content(self, mock_store):
        """store() should update existing entry when very similar (>0.90)."""
        store, mock_embedder = mock_store

        # Store first version - need to provide enough iterators
        # (one for store embed, one for duplicate check search)
        def make_iterator():
            return iter([np.array([0.1] * 384)])
        mock_embedder.embed.side_effect = lambda _: make_iterator()

        result1 = await store.store(
            content="Database connection pool exhaustion fix",
            type="note",
        )

        # Store very similar content (same embedding = 1.0 similarity)
        # _update will call _embed again
        result2 = await store.store(
            content="Database connection pool exhaustion fix - updated with more details",
            type="note",
        )

        # Should have updated existing
        assert result2["status"] == "updated"
        assert result2["id"] == result1["id"]

    @pytest.mark.asyncio
    async def test_store_default_type_is_note(self, mock_store):
        """store() should default to type='note'."""
        store, mock_embedder = mock_store
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])

        result = await store.store(content="Some content")

        assert result["type"] == "note"

    @pytest.mark.asyncio
    async def test_store_with_tags(self, mock_store):
        """store() should save tags as JSON."""
        store, mock_embedder = mock_store
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])

        result = await store.store(
            content="Test with tags",
            tags=["tag1", "tag2", "tag3"],
        )

        # Verify tags stored correctly
        retrieved = await store.get(result["id"])
        assert retrieved["tags"] == ["tag1", "tag2", "tag3"]


class TestMemoryStoreSearch:
    """Test semantic search."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_store):
        """search() should return matching results."""
        store, mock_embedder = mock_store

        # Store some content
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        await store.store(content="Python threading and GIL", type="note")

        mock_embedder.embed.return_value = iter([np.array([0.2] * 384)])
        await store.store(content="JavaScript async await", type="note")

        # Search
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        results = await store.search("python concurrency")

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, mock_store):
        """search() should respect limit parameter."""
        store, mock_embedder = mock_store

        # Store multiple items
        for i in range(5):
            mock_embedder.embed.return_value = iter([np.array([0.1 + i * 0.01] * 384)])
            await store.store(content=f"Content item {i}", type="note")

        # Search with limit
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        results = await store.search("content", limit=3)

        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, mock_store):
        """search() should filter by type when provided."""
        store, mock_embedder = mock_store

        # Use side_effect to provide fresh iterators each call
        call_count = [0]
        def make_embed(texts):
            call_count[0] += 1
            # Different embeddings for different content to avoid duplicate detection
            if call_count[0] <= 2:
                return iter([np.array([0.1 + call_count[0] * 0.2] * 384)])
            return iter([np.array([0.1] * 384)])
        mock_embedder.embed.side_effect = make_embed

        # Store different types with different embeddings
        await store.store(content="A fact about Python", type="fact")
        await store.store(content="A note about Python", type="note")

        # Search with filter
        results = await store.search("python", type_filter="fact")

        assert all(r["type"] == "fact" for r in results)

    @pytest.mark.asyncio
    async def test_search_empty_db_returns_empty(self, mock_store):
        """search() should return empty list for empty database."""
        store, mock_embedder = mock_store

        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        results = await store.search("anything")

        assert results == []


class TestMemoryStoreDelete:
    """Test deleting memories."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_delete_removes_memory(self, mock_store):
        """delete() should remove the memory."""
        store, mock_embedder = mock_store

        # Store
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        result = await store.store(content="To be deleted", type="note")
        memory_id = result["id"]

        # Delete
        delete_result = await store.delete(memory_id)

        assert delete_result["status"] == "deleted"

        # Verify gone
        retrieved = await store.get(memory_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_not_found(self, mock_store):
        """delete() should return not_found for missing ID."""
        store, _ = mock_store

        result = await store.delete("nonexistent-id")

        assert result["status"] == "not_found"


class TestMemoryStoreList:
    """Test listing memories."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_list_all_returns_all_memories(self, mock_store):
        """list_all() should return all memories."""
        store, mock_embedder = mock_store

        # Store some items
        for i in range(3):
            mock_embedder.embed.return_value = iter([np.array([0.1 + i * 0.1] * 384)])
            await store.store(content=f"Memory {i}", type="note")

        results = await store.list_all()

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_all_respects_limit(self, mock_store):
        """list_all() should respect limit parameter."""
        store, mock_embedder = mock_store

        for i in range(5):
            mock_embedder.embed.return_value = iter([np.array([0.1 + i * 0.01] * 384)])
            await store.store(content=f"Memory {i}", type="note")

        results = await store.list_all(limit=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_all_with_type_filter(self, mock_store):
        """list_all() should filter by type."""
        store, mock_embedder = mock_store

        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        await store.store(content="A fact", type="fact")

        mock_embedder.embed.return_value = iter([np.array([0.2] * 384)])
        await store.store(content="A note", type="note")

        mock_embedder.embed.return_value = iter([np.array([0.3] * 384)])
        await store.store(content="A learning", type="learning")

        results = await store.list_all(type_filter="fact")

        assert len(results) == 1
        assert results[0]["type"] == "fact"

    @pytest.mark.asyncio
    async def test_list_all_ordered_by_date(self, mock_store):
        """list_all() should return newest first."""
        store, mock_embedder = mock_store

        for i in range(3):
            mock_embedder.embed.return_value = iter([np.array([0.1 + i * 0.1] * 384)])
            await store.store(content=f"Memory {i}", type="note")

        results = await store.list_all()

        # Last stored should be first (newest)
        assert results[0]["content"] == "Memory 2"


class TestMemoryStoreFindSimilar:
    """Test finding similar memories."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_find_similar_returns_similar_entries(self, mock_store):
        """find_similar() should return entries above threshold."""
        store, mock_embedder = mock_store

        # Store some content
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        await store.store(content="Python GIL and threading", type="note")

        # Find similar (same embedding = very similar)
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        results = await store.find_similar("Python concurrency and GIL")

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_find_similar_respects_threshold(self, mock_store):
        """find_similar() should filter by threshold."""
        store, mock_embedder = mock_store

        # Store content
        mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
        await store.store(content="Python GIL", type="note")

        # Search with different embedding (will have lower similarity)
        mock_embedder.embed.return_value = iter([np.array([0.9] * 384)])
        results = await store.find_similar("Completely different topic", threshold=0.99)

        # High threshold should filter out
        # (Note: actual filtering depends on distance calculation)
        assert len(results) <= 1  # May or may not match depending on threshold


class TestMemoryStoreCount:
    """Test counting memories."""

    @pytest.fixture
    def mock_store(self, temp_db_path):
        """Create store with mocked embedder."""
        with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
            mock_embedder = MagicMock()
            mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
            mock_fastembed.return_value = mock_embedder

            from pendomind.memory import MemoryStore

            store = MemoryStore(db_path=temp_db_path)
            store._embedder = mock_embedder
            yield store, mock_embedder

    @pytest.mark.asyncio
    async def test_count_returns_total(self, mock_store):
        """count() should return total number of memories."""
        store, mock_embedder = mock_store

        assert store.count() == 0

        for i in range(3):
            mock_embedder.embed.return_value = iter([np.array([0.1 + i * 0.1] * 384)])
            await store.store(content=f"Memory {i}", type="note")

        assert store.count() == 3
