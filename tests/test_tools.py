"""Tests for PendoMind tools module - PendingStore and MCP tools."""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class TestPendingItem:
    """Test PendingItem data model."""

    def test_pending_item_creation(self):
        """PendingItem can be created with all required fields."""
        from pendomind.tools import PendingItem

        item = PendingItem(
            id="test-123",
            content="Test bug fix content",
            type="bug",
            tags=["test", "example"],
            source="github",
            file_paths=["src/api.py"],
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )

        assert item.id == "test-123"
        assert item.content == "Test bug fix content"
        assert item.type == "bug"
        assert item.tags == ["test", "example"]
        assert item.source == "github"
        assert item.file_paths == ["src/api.py"]
        assert len(item.embedding) == 1536

    def test_pending_item_has_created_at(self):
        """PendingItem should have auto-generated created_at timestamp."""
        from pendomind.tools import PendingItem

        before = _utc_now()
        item = PendingItem(
            id="test-123",
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )
        after = _utc_now()

        assert before <= item.created_at <= after

    def test_pending_item_is_expired_fresh(self):
        """Fresh item should not be expired."""
        from pendomind.tools import PendingItem

        item = PendingItem(
            id="test-123",
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )

        assert item.is_expired(ttl_minutes=30) is False

    def test_pending_item_is_expired_old(self):
        """Old item should be expired."""
        from pendomind.tools import PendingItem

        item = PendingItem(
            id="test-123",
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
            created_at=_utc_now() - timedelta(minutes=60),
        )

        assert item.is_expired(ttl_minutes=30) is True

    def test_pending_item_optional_duplicate_info(self):
        """PendingItem can have optional duplicate_info."""
        from pendomind.tools import PendingItem

        item = PendingItem(
            id="test-123",
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
            duplicate_info={"similar_id": "existing-456", "similarity": 0.92},
        )

        assert item.duplicate_info is not None
        assert item.duplicate_info["similarity"] == 0.92


class TestPendingStore:
    """Test pending item storage with TTL."""

    @pytest.fixture
    def store(self):
        from pendomind.tools import PendingStore

        return PendingStore(ttl_minutes=30)

    @pytest.fixture
    def sample_item(self):
        from pendomind.tools import PendingItem

        return PendingItem(
            id="test-123",
            content="Test content for bug fix",
            type="bug",
            tags=["test", "example"],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )

    def test_add_and_retrieve_item(self, store, sample_item):
        """Should add and retrieve pending items by ID."""
        store.add(sample_item)
        retrieved = store.get("test-123")

        assert retrieved is not None
        assert retrieved.id == "test-123"
        assert retrieved.content == "Test content for bug fix"
        assert retrieved.type == "bug"

    def test_get_nonexistent_returns_none(self, store):
        """Getting non-existent ID should return None."""
        result = store.get("nonexistent-id")

        assert result is None

    def test_remove_item(self, store, sample_item):
        """Should remove pending items successfully."""
        store.add(sample_item)
        result = store.remove("test-123")

        assert result is True
        assert store.get("test-123") is None

    def test_remove_nonexistent_returns_false(self, store):
        """Removing non-existent item should return False."""
        result = store.remove("nonexistent-id")

        assert result is False

    def test_expired_item_returns_none(self, store):
        """Items past TTL should return None."""
        from pendomind.tools import PendingItem

        expired_item = PendingItem(
            id="expired-123",
            content="Old content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
            created_at=_utc_now() - timedelta(minutes=60),
        )
        store.add(expired_item)

        result = store.get("expired-123")

        assert result is None

    def test_list_pending_returns_all_valid(self, store, sample_item):
        """list_pending() should return all non-expired items."""
        from pendomind.tools import PendingItem

        # Add two fresh items
        store.add(sample_item)
        another_item = PendingItem(
            id="test-456",
            content="Another content",
            type="feature",
            tags=["test"],
            source="confluence",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )
        store.add(another_item)

        pending = store.list_pending()

        assert len(pending) == 2
        ids = [item.id for item in pending]
        assert "test-123" in ids
        assert "test-456" in ids

    def test_list_pending_excludes_expired(self, store, sample_item):
        """list_pending() should only return non-expired items."""
        from pendomind.tools import PendingItem

        # Add fresh item
        store.add(sample_item)

        # Add expired item directly to bypass add() validation
        expired = PendingItem(
            id="expired-123",
            content="Old content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
            created_at=_utc_now() - timedelta(minutes=60),
        )
        store._items["expired-123"] = expired

        pending = store.list_pending()

        assert len(pending) == 1
        assert pending[0].id == "test-123"

    def test_cleanup_expired_removes_old_items(self, store, sample_item):
        """cleanup_expired() should remove expired items."""
        from pendomind.tools import PendingItem

        # Add fresh item
        store.add(sample_item)

        # Add expired items directly
        for i in range(3):
            expired = PendingItem(
                id=f"expired-{i}",
                content="Old content",
                type="bug",
                tags=[],
                source="github",
                file_paths=None,
                embedding=[0.1] * 1536,
                quality_analysis=MagicMock(),
                created_at=_utc_now() - timedelta(minutes=60),
            )
            store._items[f"expired-{i}"] = expired

        # Should have 4 items total
        assert len(store._items) == 4

        # Cleanup
        removed_count = store.cleanup_expired()

        # Should have removed 3 expired items
        assert removed_count == 3
        assert len(store._items) == 1
        assert "test-123" in store._items

    def test_count_pending(self, store, sample_item):
        """count() should return number of valid pending items."""
        from pendomind.tools import PendingItem

        store.add(sample_item)
        another = PendingItem(
            id="test-456",
            content="Another",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )
        store.add(another)

        assert store.count() == 2

    def test_count_excludes_expired(self, store, sample_item):
        """count() should not include expired items."""
        from pendomind.tools import PendingItem

        store.add(sample_item)

        # Add expired item directly
        expired = PendingItem(
            id="expired-123",
            content="Old",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
            created_at=_utc_now() - timedelta(minutes=60),
        )
        store._items["expired-123"] = expired

        assert store.count() == 1

    def test_store_uses_config_ttl(self):
        """Store should use TTL from config if provided."""
        from pendomind.tools import PendingStore
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        config.pending.ttl_minutes = 45
        store = PendingStore(config=config)

        assert store.ttl_minutes == 45

    def test_store_overrides_config_ttl(self):
        """Explicit TTL should override config TTL."""
        from pendomind.tools import PendingStore
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        config.pending.ttl_minutes = 45
        store = PendingStore(ttl_minutes=60, config=config)

        assert store.ttl_minutes == 60

    def test_add_generates_id_if_not_provided(self, store):
        """Add should work with items that need ID generation."""
        from pendomind.tools import PendingItem

        item = PendingItem(
            id="",  # Empty ID
            content="Test content",
            type="bug",
            tags=[],
            source="github",
            file_paths=None,
            embedding=[0.1] * 1536,
            quality_analysis=MagicMock(),
        )

        generated_id = store.add(item)

        assert generated_id is not None
        assert len(generated_id) > 0
        assert store.get(generated_id) is not None


class TestSearchTool:
    """Test the search MCP tool."""

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock_instance = MagicMock()
        mock_instance.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        mock_instance.search = AsyncMock(
            return_value=[
                {
                    "id": "result-1",
                    "score": 0.95,
                    "content": "Bug fix for database timeout",
                    "type": "bug",
                    "tags": ["db"],
                    "source": "github",
                },
                {
                    "id": "result-2",
                    "score": 0.82,
                    "content": "Another related fix",
                    "type": "bug",
                    "tags": ["db"],
                    "source": "confluence",
                },
            ]
        )
        return mock_instance

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_kb):
        """search() should return formatted search results."""
        from pendomind.tools import search

        results = await search("database timeout", kb=mock_kb)

        assert len(results) == 2
        assert results[0]["id"] == "result-1"
        assert results[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, mock_kb):
        """search() should pass type filter to KB."""
        from pendomind.tools import search

        await search("database", type_filter="incident", kb=mock_kb)

        mock_kb.search.assert_called_once()
        call_kwargs = mock_kb.search.call_args[1]
        assert call_kwargs["type_filter"] == "incident"

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, mock_kb):
        """search() should pass limit to KB."""
        from pendomind.tools import search

        await search("query", limit=5, kb=mock_kb)

        call_kwargs = mock_kb.search.call_args[1]
        assert call_kwargs["limit"] == 5


class TestRememberTool:
    """Test the remember MCP tool."""

    @pytest.fixture
    def mock_middleware(self):
        """Mock quality middleware."""
        mock = MagicMock()
        mock.process = AsyncMock(
            return_value={
                "status": "stored",
                "id": "stored-123",
                "quality_score": 0.91,
            }
        )
        return mock

    @pytest.mark.asyncio
    async def test_remember_uses_middleware(self, mock_middleware):
        """remember() should use quality middleware for processing."""
        from pendomind.tools import remember

        result = await remember(
            content="Fixed the database connection pool exhaustion issue by increasing pool size from 10 to 50 and adding connection timeout handling.",
            type="bug",
            tags=["database", "performance"],
            source="github",
            middleware=mock_middleware,
        )

        mock_middleware.process.assert_called_once()
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_remember_returns_pending(self, mock_middleware):
        """remember() should return pending status for medium quality."""
        mock_middleware.process = AsyncMock(
            return_value={
                "status": "pending",
                "pending_id": "pending-456",
                "quality_score": 0.72,
                "recommendations": ["Add more context"],
            }
        )

        from pendomind.tools import remember

        result = await remember(
            content="Fixed authentication issue.",
            type="bug",
            tags=[],
            source="slack",
            middleware=mock_middleware,
        )

        assert result["status"] == "pending"
        assert result["pending_id"] == "pending-456"

    @pytest.mark.asyncio
    async def test_remember_returns_rejected(self, mock_middleware):
        """remember() should return rejected status for low quality."""
        mock_middleware.process = AsyncMock(
            return_value={
                "status": "rejected",
                "message": "Quality score 0.45 below threshold 0.65",
                "quality_score": 0.45,
            }
        )

        from pendomind.tools import remember

        result = await remember(
            content="Fixed bug.",
            type="bug",
            tags=[],
            source="slack",
            middleware=mock_middleware,
        )

        assert result["status"] == "rejected"


class TestRememberConfirmTool:
    """Test the remember_confirm MCP tool."""

    @pytest.fixture
    def mock_pending_store(self):
        """Mock pending store with item."""
        from pendomind.tools import PendingItem

        mock = MagicMock()
        mock.get = MagicMock(
            return_value=PendingItem(
                id="pending-123",
                content="Test content for storage",
                type="bug",
                tags=["test"],
                source="github",
                file_paths=["src/api.py"],
                embedding=[0.1] * 1536,
                quality_analysis=MagicMock(),
            )
        )
        mock.remove = MagicMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock = MagicMock()
        mock.store = AsyncMock(return_value="stored-789")
        return mock

    @pytest.mark.asyncio
    async def test_confirm_approve_stores_content(self, mock_pending_store, mock_kb):
        """Approving should store content in KB."""
        from pendomind.tools import remember_confirm

        result = await remember_confirm(
            pending_id="pending-123",
            approved=True,
            pending_store=mock_pending_store,
            kb=mock_kb,
        )

        mock_kb.store.assert_called_once()
        mock_pending_store.remove.assert_called_with("pending-123")
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_confirm_reject_removes_from_pending(
        self, mock_pending_store, mock_kb
    ):
        """Rejecting should remove from pending without storing."""
        from pendomind.tools import remember_confirm

        result = await remember_confirm(
            pending_id="pending-123",
            approved=False,
            pending_store=mock_pending_store,
            kb=mock_kb,
        )

        mock_kb.store.assert_not_called()
        mock_pending_store.remove.assert_called_with("pending-123")
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_confirm_expired_returns_error(self, mock_kb):
        """Confirming expired item should return error."""
        from pendomind.tools import remember_confirm, PendingStore

        mock_store = MagicMock()
        mock_store.get = MagicMock(return_value=None)  # Not found (expired)

        result = await remember_confirm(
            pending_id="expired-123",
            approved=True,
            pending_store=mock_store,
            kb=mock_kb,
        )

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestRecallTool:
    """Test the recall MCP tool."""

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock = MagicMock()
        mock.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        mock.search = AsyncMock(
            return_value=[
                {
                    "id": "entry-1",
                    "score": 0.92,
                    "content": "Database connection pooling best practices...",
                    "type": "architecture",
                    "tags": ["database"],
                },
            ]
        )
        return mock

    @pytest.mark.asyncio
    async def test_recall_returns_formatted_context(self, mock_kb):
        """recall() should return formatted context from KB."""
        from pendomind.tools import recall

        result = await recall("database connection issues", kb=mock_kb)

        assert "entries" in result
        assert len(result["entries"]) == 1
        assert result["entries"][0]["content"].startswith("Database")

    @pytest.mark.asyncio
    async def test_recall_with_type_filter(self, mock_kb):
        """recall() should filter by type."""
        from pendomind.tools import recall

        await recall("query", type_filter="incident", kb=mock_kb)

        call_kwargs = mock_kb.search.call_args[1]
        assert call_kwargs["type_filter"] == "incident"


class TestListSimilarTool:
    """Test the list_similar MCP tool."""

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock = MagicMock()
        mock.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        mock.find_duplicates = AsyncMock(
            return_value=[
                {
                    "id": "similar-1",
                    "similarity_score": 0.95,
                    "content_preview": "Very similar content...",
                    "type": "bug",
                },
            ]
        )
        return mock

    @pytest.mark.asyncio
    async def test_list_similar_finds_duplicates(self, mock_kb):
        """list_similar() should return potential duplicates."""
        from pendomind.tools import list_similar

        result = await list_similar(
            "Fixed database connection timeout issue", kb=mock_kb
        )

        assert len(result) == 1
        assert result[0]["similarity_score"] == 0.95

    @pytest.mark.asyncio
    async def test_list_similar_empty_when_unique(self, mock_kb):
        """list_similar() should return empty list for unique content."""
        mock_kb.find_duplicates = AsyncMock(return_value=[])

        from pendomind.tools import list_similar

        result = await list_similar("Completely unique content here", kb=mock_kb)

        assert len(result) == 0


class TestGetContextTool:
    """Test the get_context MCP tool."""

    @pytest.fixture
    def mock_kb(self):
        """Mock knowledge base."""
        mock = MagicMock()
        mock.get_by_file_path = AsyncMock(
            return_value=[
                {
                    "id": "entry-1",
                    "content": "Bug fix in api.py: Fixed rate limiting",
                    "type": "bug",
                    "file_paths": ["src/api.py"],
                },
                {
                    "id": "entry-2",
                    "content": "Feature: Added caching to api.py",
                    "type": "feature",
                    "file_paths": ["src/api.py"],
                },
            ]
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_context_returns_file_related_entries(self, mock_kb):
        """get_context() should return knowledge related to file."""
        from pendomind.tools import get_context

        result = await get_context("src/api.py", kb=mock_kb)

        assert "entries" in result
        assert len(result["entries"]) == 2
        mock_kb.get_by_file_path.assert_called_with("src/api.py")

    @pytest.mark.asyncio
    async def test_get_context_empty_for_new_file(self, mock_kb):
        """get_context() should return empty for files with no entries."""
        mock_kb.get_by_file_path = AsyncMock(return_value=[])

        from pendomind.tools import get_context

        result = await get_context("new/file.py", kb=mock_kb)

        assert result["entries"] == []
