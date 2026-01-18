"""MCP tools and PendingStore for PendoMind knowledge base."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pendomind.config import PendoMindConfig


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class PendingItem:
    """A pending knowledge entry awaiting user confirmation.

    Items in the "pending" state have quality scores between 0.65-0.85
    and require explicit user approval before storage.
    """

    id: str
    content: str
    type: str
    tags: list[str]
    source: str
    file_paths: list[str] | None
    embedding: list[float]
    quality_analysis: Any  # QualityAnalysis or mock
    duplicate_info: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """Check if this pending item has expired.

        Args:
            ttl_minutes: Time-to-live in minutes

        Returns:
            True if item is past TTL, False otherwise
        """
        # Handle both timezone-aware and naive datetimes
        now = _utc_now()
        if self.created_at.tzinfo is None:
            # If created_at is naive, make comparison in naive UTC
            now = now.replace(tzinfo=None)
        expiry_time = self.created_at + timedelta(minutes=ttl_minutes)
        return now > expiry_time


class PendingStore:
    """In-memory store for pending knowledge entries with TTL.

    Stores items awaiting user confirmation. Items expire after TTL
    and are automatically cleaned up.

    The store is intentionally in-memory (not persistent) because:
    - Pending items are transient by design
    - User should confirm promptly while context is fresh
    - No need to survive restarts
    """

    def __init__(
        self, ttl_minutes: int | None = None, config: PendoMindConfig | None = None
    ):
        """Initialize the pending store.

        Args:
            ttl_minutes: Override TTL (optional)
            config: PendoMindConfig for default TTL (optional)
        """
        self._items: dict[str, PendingItem] = {}

        # Determine TTL: explicit > config > default
        if ttl_minutes is not None:
            self.ttl_minutes = ttl_minutes
        elif config is not None:
            self.ttl_minutes = config.pending.ttl_minutes
        else:
            self.ttl_minutes = 30  # Default

    def add(self, item: PendingItem) -> str:
        """Add a pending item to the store.

        Args:
            item: The pending item to store

        Returns:
            The item ID (generated if empty)
        """
        # Generate ID if not provided
        if not item.id:
            item.id = f"pending-{uuid.uuid4().hex[:12]}"

        self._items[item.id] = item
        return item.id

    def get(self, item_id: str) -> PendingItem | None:
        """Retrieve a pending item by ID.

        Returns None if item doesn't exist or has expired.

        Args:
            item_id: The ID of the pending item

        Returns:
            PendingItem if found and valid, None otherwise
        """
        item = self._items.get(item_id)
        if item is None:
            return None

        # Check if expired
        if item.is_expired(self.ttl_minutes):
            # Auto-cleanup expired item
            del self._items[item_id]
            return None

        return item

    def remove(self, item_id: str) -> bool:
        """Remove a pending item from the store.

        Args:
            item_id: The ID of the item to remove

        Returns:
            True if item was removed, False if not found
        """
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def list_pending(self) -> list[PendingItem]:
        """List all non-expired pending items.

        Returns:
            List of valid pending items
        """
        valid_items = []
        expired_ids = []

        for item_id, item in self._items.items():
            if item.is_expired(self.ttl_minutes):
                expired_ids.append(item_id)
            else:
                valid_items.append(item)

        # Cleanup expired items
        for item_id in expired_ids:
            del self._items[item_id]

        return valid_items

    def cleanup_expired(self) -> int:
        """Remove all expired items from the store.

        Returns:
            Number of items removed
        """
        expired_ids = [
            item_id
            for item_id, item in self._items.items()
            if item.is_expired(self.ttl_minutes)
        ]

        for item_id in expired_ids:
            del self._items[item_id]

        return len(expired_ids)

    def count(self) -> int:
        """Count non-expired pending items.

        Returns:
            Number of valid pending items
        """
        return sum(
            1
            for item in self._items.values()
            if not item.is_expired(self.ttl_minutes)
        )


# --------------------------------------------------------------------------
# MCP Tools
# --------------------------------------------------------------------------
# These functions are the MCP tool implementations that will be exposed via
# FastMCP decorators in main.py. They accept optional dependency injection
# for testing purposes.


async def search(
    query: str,
    type_filter: str | None = None,
    limit: int = 10,
    kb: Any | None = None,
) -> list[dict[str, Any]]:
    """Search the knowledge base for relevant entries.

    Args:
        query: Natural language search query
        type_filter: Optional type to filter results (bug, feature, etc.)
        limit: Maximum number of results to return
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        List of matching knowledge entries with scores
    """
    # Lazy import to avoid circular dependencies
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    # Generate embedding for query
    embedding = await kb.get_embedding(query)

    # Search knowledge base
    results = await kb.search(embedding, type_filter=type_filter, limit=limit)

    return results


async def remember(
    content: str,
    type: str,
    tags: list[str],
    source: str = "claude_session",
    file_paths: list[str] | None = None,
    middleware: Any | None = None,
) -> dict[str, Any]:
    """Store knowledge with quality control.

    Processes content through quality middleware:
    - Score < 0.65: Auto-reject
    - Score 0.65-0.85: Pending (requires confirm)
    - Score > 0.85: Auto-approve

    Args:
        content: The knowledge to store
        type: Knowledge type (bug, feature, incident, etc.)
        tags: List of tags for categorization
        source: Source of the content (github, slack, etc.)
        file_paths: Related file paths
        middleware: QualityMiddleware instance (injected for testing)

    Returns:
        Result dict with status and details
    """
    # Lazy import to avoid circular dependencies
    if middleware is None:
        from pendomind.middleware import QualityMiddleware

        middleware = QualityMiddleware()

    # Process through quality middleware
    result = await middleware.process(
        content=content,
        type=type,
        tags=tags,
        source=source,
        file_paths=file_paths,
    )

    return result


async def remember_confirm(
    pending_id: str,
    approved: bool,
    pending_store: PendingStore | None = None,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Confirm or reject a pending knowledge entry.

    Args:
        pending_id: ID of the pending item
        approved: True to store, False to discard
        pending_store: PendingStore instance (injected for testing)
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Result dict with status
    """
    # Lazy imports
    if pending_store is None:
        pending_store = PendingStore()
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    # Get pending item
    item = pending_store.get(pending_id)
    if item is None:
        return {
            "status": "error",
            "message": f"Pending item '{pending_id}' not found or expired",
        }

    if approved:
        # Store in knowledge base
        point_id = await kb.store(
            content=item.content,
            type=item.type,
            tags=item.tags,
            source=item.source,
            file_paths=item.file_paths,
            embedding=item.embedding,
        )
        pending_store.remove(pending_id)
        return {"status": "stored", "id": point_id}
    else:
        # Reject - just remove from pending
        pending_store.remove(pending_id)
        return {"status": "rejected", "message": "User rejected the entry"}


async def recall(
    query: str,
    type_filter: str | None = None,
    limit: int = 5,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Retrieve relevant context from knowledge base.

    Similar to search but returns formatted context suitable for
    including in prompts.

    Args:
        query: Natural language query
        type_filter: Optional type filter
        limit: Maximum entries to return
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Dict with formatted context entries
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    embedding = await kb.get_embedding(query)
    results = await kb.search(embedding, type_filter=type_filter, limit=limit)

    return {"entries": results, "query": query, "count": len(results)}


async def list_similar(
    content: str,
    threshold: float | None = None,
    kb: Any | None = None,
) -> list[dict[str, Any]]:
    """Find similar entries before storing.

    Use this to check for duplicates before calling remember().

    Args:
        content: Content to check for duplicates
        threshold: Similarity threshold (default from config)
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        List of similar entries above threshold
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    embedding = await kb.get_embedding(content)
    duplicates = await kb.find_duplicates(embedding, threshold=threshold)

    return duplicates


async def get_context(
    file_path: str,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Get knowledge related to a specific file.

    Args:
        file_path: Path to the file
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Dict with entries related to this file
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    entries = await kb.get_by_file_path(file_path)

    return {"entries": entries, "file_path": file_path, "count": len(entries)}


async def list_all(
    limit: int = 100,
    type_filter: str | None = None,
    kb: Any | None = None,
) -> list[dict[str, Any]]:
    """List all knowledge entries with summaries.

    Returns entries with truncated content for quick scanning.

    Args:
        limit: Maximum entries to return
        type_filter: Optional type filter (bug, feature, etc.)
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        List of entries with summary previews
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    entries = await kb.get_all(type_filter=type_filter, limit=limit)

    return [
        {
            "id": entry["id"],
            "type": entry.get("type"),
            "summary": (
                entry.get("content", "")[:150] + "..."
                if len(entry.get("content", "")) > 150
                else entry.get("content", "")
            ),
            "tags": entry.get("tags", []),
            "source": entry.get("source"),
            "file_paths": entry.get("file_paths"),
            "created_at": entry.get("created_at"),
        }
        for entry in entries
    ]


async def update(
    id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    type: str | None = None,
    file_paths: list[str] | None = None,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Update an existing knowledge entry by ID.

    Only provided fields are updated; others remain unchanged.
    If content changes, the entry is re-embedded for accurate search.

    Args:
        id: ID of the entry to update
        content: New content (triggers re-embedding if provided)
        tags: New tags list
        type: New type
        file_paths: New file paths list
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Updated entry dict

    Raises:
        ValueError: If entry not found
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    return await kb.update(
        point_id=id,
        content=content,
        tags=tags,
        type=type,
        file_paths=file_paths,
    )


async def delete(
    id: str,
    kb: Any | None = None,
) -> dict[str, str]:
    """Delete a knowledge entry by ID.

    Args:
        id: ID of the entry to delete
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Status dict
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    await kb.delete(id)
    return {"status": "deleted", "id": id}


async def upsert(
    content: str,
    type: str,
    tags: list[str],
    source: str = "claude_session",
    file_paths: list[str] | None = None,
    similarity_threshold: float = 0.85,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Smart update-or-create: finds similar entry and updates it, or creates new.

    This is the recommended tool when you want to update an existing entry
    but don't have the exact ID. It automatically:
    1. Searches for similar existing entries
    2. If a match above threshold is found, updates that entry
    3. If no match, creates a new entry

    Args:
        content: The knowledge content
        type: Knowledge type (bug, feature, incident, etc.)
        tags: List of tags for categorization
        source: Source of the content
        file_paths: Related file paths
        similarity_threshold: How similar an existing entry must be to update (default 0.85)
        kb: KnowledgeBase instance (injected for testing)

    Returns:
        Result dict with status ('updated' or 'created'), id, and details
    """
    if kb is None:
        from pendomind.knowledge import KnowledgeBase

        kb = KnowledgeBase()

    # Generate embedding for the new content
    embedding = await kb.get_embedding(content)

    # Search for similar existing entries
    similar = await kb.find_duplicates(embedding, threshold=similarity_threshold)

    if similar:
        # Found a similar entry - update it
        existing = similar[0]  # Take the most similar one
        existing_id = existing["id"]

        updated = await kb.update(
            point_id=existing_id,
            content=content,
            tags=tags,
            type=type,
            file_paths=file_paths,
        )

        return {
            "status": "updated",
            "id": existing_id,
            "previous_similarity": existing["similarity_score"],
            "previous_content_preview": existing.get("content_preview", ""),
            **updated,
        }
    else:
        # No similar entry found - create new
        point_id = await kb.store(
            content=content,
            type=type,
            tags=tags,
            source=source,
            file_paths=file_paths,
            embedding=embedding,
        )

        return {
            "status": "created",
            "id": point_id,
            "content": content,
            "type": type,
            "tags": tags,
            "source": source,
            "file_paths": file_paths,
        }
