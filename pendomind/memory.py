"""SQLite-backed memory persistence with vector search.

Uses sqlite-vec extension for semantic search capabilities.
Uses APSW (Another Python SQLite Wrapper) for extension loading support.
Zero setup required - just works with a local file.
"""

import hashlib
import json
import struct
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import apsw
from fastembed import TextEmbedding
import sqlite_vec


def _serialize_f32(vector: list[float]) -> bytes:
    """Serialize a list of floats to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def _deserialize_f32(blob: bytes) -> list[float]:
    """Deserialize bytes back to a list of floats."""
    n = len(blob) // 4  # 4 bytes per float32
    return list(struct.unpack(f"{n}f", blob))


class MemoryStore:
    """SQLite-backed memory persistence with vector search.

    Features:
    - Semantic search using FastEmbed + sqlite-vec
    - Auto-deduplication by content similarity
    - Simple CRUD operations
    - Zero external dependencies (no Docker)

    Storage location: ~/.pendomind/memory.db (configurable)
    """

    EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMS = 384

    def __init__(self, db_path: str | Path | None = None):
        """Initialize memory store.

        Args:
            db_path: Path to SQLite database file.
                     Defaults to ~/.pendomind/memory.db
        """
        if db_path is None:
            db_path = Path.home() / ".pendomind" / "memory.db"
        self.db_path = Path(db_path).expanduser()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

        # Initialize embedder (lazy - downloads model on first use)
        self._embedder: TextEmbedding | None = None

    def _get_connection(self) -> apsw.Connection:
        """Get a database connection with sqlite-vec loaded."""
        conn = apsw.Connection(str(self.db_path))
        conn.enable_load_extension(True)
        conn.load_extension(sqlite_vec.loadable_path())
        conn.enable_load_extension(False)
        return conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Main metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'note',
                    tags TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)

            # Indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_type
                ON memories(type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_created
                ON memories(created_at DESC)
            """)

            # Vector storage table (sqlite-vec virtual table)
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec
                USING vec0(embedding float[{self.EMBEDDING_DIMS}])
            """)

            # Mapping table for id -> vector rowid
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    memory_id TEXT PRIMARY KEY,
                    vec_rowid INTEGER NOT NULL
                )
            """)
        finally:
            conn.close()

    @property
    def embedder(self) -> TextEmbedding:
        """Lazy-initialize embedder on first use."""
        if self._embedder is None:
            self._embedder = TextEmbedding(model_name=self.EMBEDDING_MODEL)
        return self._embedder

    def _embed(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            384-dimensional embedding vector
        """
        embeddings = list(self.embedder.embed([text]))
        return embeddings[0].tolist()

    def _generate_id(self, content: str) -> str:
        """Generate deterministic ID from content.

        Same content always produces same ID, enabling idempotent stores.

        Args:
            content: The content to hash

        Returns:
            UUID-formatted ID
        """
        hex_digest = hashlib.sha256(content.encode()).hexdigest()[:32]
        return str(uuid.UUID(hex_digest))

    async def store(
        self,
        content: str,
        type: str = "note",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store a memory.

        Automatically handles deduplication:
        - If very similar content exists (>0.90 similarity), updates it
        - Otherwise creates new entry

        Args:
            content: What to remember
            type: Memory type (fact, note, learning). Default: note
            tags: Optional tags for categorization

        Returns:
            Dict with status, id, and stored content
        """
        embedding = self._embed(content)

        # Check for duplicates
        similar = await self._find_similar_internal(embedding, threshold=0.90, limit=1)
        if similar:
            # Update existing entry
            existing_id = similar[0]["id"]
            return await self._update(existing_id, content, type, tags)

        # Create new entry
        return await self._insert(content, type, tags, embedding)

    async def _insert(
        self,
        content: str,
        type: str,
        tags: list[str] | None,
        embedding: list[float],
    ) -> dict[str, Any]:
        """Insert a new memory entry.

        Args:
            content: Memory content
            type: Memory type
            tags: Optional tags
            embedding: Pre-computed embedding vector

        Returns:
            Dict with status and entry details
        """
        memory_id = self._generate_id(content)
        created_at = datetime.now(UTC).isoformat()
        tags_json = json.dumps(tags) if tags else None

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Insert into vector table first to get rowid
            cursor.execute(
                "INSERT INTO memories_vec(embedding) VALUES (?)",
                (_serialize_f32(embedding),)
            )
            vec_rowid = conn.last_insert_rowid()

            # Insert metadata
            cursor.execute(
                """
                INSERT INTO memories (id, content, type, tags, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memory_id, content, type, tags_json, created_at)
            )

            # Store the mapping (id -> vec_rowid)
            cursor.execute(
                "INSERT OR REPLACE INTO memory_vectors (memory_id, vec_rowid) VALUES (?, ?)",
                (memory_id, vec_rowid)
            )

            return {
                "status": "created",
                "id": memory_id,
                "content": content,
                "type": type,
                "tags": tags,
                "created_at": created_at,
            }
        finally:
            conn.close()

    async def _update(
        self,
        memory_id: str,
        content: str,
        type: str,
        tags: list[str] | None,
    ) -> dict[str, Any]:
        """Update an existing memory entry.

        Re-embeds content and updates both metadata and vector.

        Args:
            memory_id: ID of entry to update
            content: New content
            type: New type
            tags: New tags

        Returns:
            Dict with status and updated entry details
        """
        embedding = self._embed(content)
        updated_at = datetime.now(UTC).isoformat()
        tags_json = json.dumps(tags) if tags else None

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Get the vec_rowid for this memory
            cursor.execute(
                "SELECT vec_rowid FROM memory_vectors WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if row:
                vec_rowid = row[0]
                # Update vector
                cursor.execute(
                    "UPDATE memories_vec SET embedding = ? WHERE rowid = ?",
                    (_serialize_f32(embedding), vec_rowid)
                )

            # Update metadata
            cursor.execute(
                """
                UPDATE memories
                SET content = ?, type = ?, tags = ?, updated_at = ?
                WHERE id = ?
                """,
                (content, type, tags_json, updated_at, memory_id)
            )

            # Get created_at for response
            cursor.execute(
                "SELECT created_at FROM memories WHERE id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()
            created_at = row[0] if row else None

            return {
                "status": "updated",
                "id": memory_id,
                "content": content,
                "type": type,
                "tags": tags,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        finally:
            conn.close()

    async def search(
        self,
        query: str,
        limit: int = 10,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for memories.

        Args:
            query: Natural language search query
            limit: Maximum results (default: 10)
            type_filter: Optional filter by type

        Returns:
            List of matching memories with similarity scores
        """
        embedding = self._embed(query)
        return await self._knn_search(embedding, limit, type_filter)

    async def _knn_search(
        self,
        embedding: list[float],
        limit: int,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """K-nearest neighbor search using sqlite-vec.

        Args:
            embedding: Query vector
            limit: Max results
            type_filter: Optional type filter

        Returns:
            List of matching entries with scores
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # First get nearest vectors
            # sqlite-vec returns distance (lower = more similar for L2)
            # We convert to similarity score (higher = more similar)
            cursor.execute(
                """
                SELECT rowid, distance
                FROM memories_vec
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (_serialize_f32(embedding), limit * 2)  # Get extra for filtering
            )
            vector_results = list(cursor.fetchall())

            if not vector_results:
                return []

            # Get the memory IDs for these rowids
            rowids = [r[0] for r in vector_results]
            distances = {r[0]: r[1] for r in vector_results}

            # Fetch memory metadata
            placeholders = ",".join("?" * len(rowids))
            query_sql = f"""
                SELECT m.id, m.content, m.type, m.tags, m.created_at, m.updated_at, mv.vec_rowid
                FROM memories m
                JOIN memory_vectors mv ON m.id = mv.memory_id
                WHERE mv.vec_rowid IN ({placeholders})
            """
            params: list[Any] = list(rowids)

            if type_filter:
                query_sql = f"""
                    SELECT m.id, m.content, m.type, m.tags, m.created_at, m.updated_at, mv.vec_rowid
                    FROM memories m
                    JOIN memory_vectors mv ON m.id = mv.memory_id
                    WHERE mv.vec_rowid IN ({placeholders}) AND m.type = ?
                """
                params.append(type_filter)

            cursor.execute(query_sql, params)
            rows = list(cursor.fetchall())

            # Build results with similarity scores
            results = []
            for row in rows:
                id_, content, type_, tags_json, created_at, updated_at, vec_rowid = row
                distance = distances.get(vec_rowid, 0)
                # Convert L2 distance to similarity (1 / (1 + distance))
                similarity = 1 / (1 + distance)

                tags = json.loads(tags_json) if tags_json else []
                results.append({
                    "id": id_,
                    "content": content,
                    "type": type_,
                    "tags": tags,
                    "score": round(similarity, 4),
                    "created_at": created_at,
                    "updated_at": updated_at,
                })

            # Sort by similarity and limit
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        finally:
            conn.close()

    async def _find_similar_internal(
        self,
        embedding: list[float],
        threshold: float = 0.90,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar entries by embedding (internal use).

        Args:
            embedding: Pre-computed embedding vector
            threshold: Minimum similarity score
            limit: Max results

        Returns:
            List of similar entries above threshold
        """
        results = await self._knn_search(embedding, limit)
        return [r for r in results if r["score"] >= threshold]

    async def find_similar(
        self,
        content: str,
        threshold: float = 0.85,
    ) -> list[dict[str, Any]]:
        """Find similar memories by content.

        Use this to check for duplicates before storing.

        Args:
            content: Content to check
            threshold: Minimum similarity score (default: 0.85)

        Returns:
            List of similar entries above threshold
        """
        embedding = self._embed(content)
        return await self._find_similar_internal(embedding, threshold, limit=5)

    async def delete(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id: ID of memory to delete

        Returns:
            Dict with status
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Get vec_rowid first
            cursor.execute(
                "SELECT vec_rowid FROM memory_vectors WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if row:
                vec_rowid = row[0]
                # Delete from vector table
                cursor.execute(
                    "DELETE FROM memories_vec WHERE rowid = ?",
                    (vec_rowid,)
                )
                # Delete from mapping table
                cursor.execute(
                    "DELETE FROM memory_vectors WHERE memory_id = ?",
                    (memory_id,)
                )

            # Delete from main table
            cursor.execute(
                "DELETE FROM memories WHERE id = ?",
                (memory_id,)
            )
            deleted_count = conn.changes()

            if deleted_count == 0:
                return {"status": "not_found", "id": memory_id}

            return {"status": "deleted", "id": memory_id}

        finally:
            conn.close()

    async def list_all(
        self,
        limit: int = 50,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all memories.

        Args:
            limit: Maximum results (default: 50)
            type_filter: Optional filter by type

        Returns:
            List of memories ordered by creation date (newest first)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            query = "SELECT id, content, type, tags, created_at, updated_at FROM memories"
            params: list[Any] = []

            if type_filter:
                query += " WHERE type = ?"
                params.append(type_filter)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = list(cursor.fetchall())

            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "type": row[2],
                    "tags": json.loads(row[3]) if row[3] else [],
                    "created_at": row[4],
                    "updated_at": row[5],
                }
                for row in rows
            ]

        finally:
            conn.close()

    async def get(self, memory_id: str) -> dict[str, Any] | None:
        """Get a memory by ID.

        Args:
            memory_id: ID of memory to retrieve

        Returns:
            Memory dict or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, content, type, tags, created_at, updated_at FROM memories WHERE id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "content": row[1],
                "type": row[2],
                "tags": json.loads(row[3]) if row[3] else [],
                "created_at": row[4],
                "updated_at": row[5],
            }

        finally:
            conn.close()

    def count(self) -> int:
        """Count total memories.

        Returns:
            Number of stored memories
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM memories")
            row = cursor.fetchone()
            return row[0]
        finally:
            conn.close()
