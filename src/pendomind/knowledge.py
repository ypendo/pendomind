"""Knowledge base wrapper for Qdrant vector database."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from pendomind.config import PendoMindConfig


class KnowledgeBase:
    """Qdrant-backed knowledge base for engineering knowledge.

    Handles:
    - Collection initialization with proper vector config
    - Storing knowledge entries with deterministic IDs
    - Semantic search with optional type filtering
    - Duplicate detection via similarity threshold
    - File path based retrieval
    """

    def __init__(self, config: PendoMindConfig | None = None):
        """Initialize knowledge base with Qdrant connection.

        Args:
            config: PendoMindConfig for connection settings
        """
        self.config = config or PendoMindConfig()

        # Initialize Qdrant client
        self._client = QdrantClient(
            host=self.config.qdrant.host,
            port=self.config.qdrant.port,
        )

        # Initialize FastEmbed for local embeddings (no API key needed)
        # Model is downloaded from HuggingFace Hub on first use, then cached
        self._embedder = TextEmbedding(model_name=self.config.embeddings.model)

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collection_name = self.config.qdrant.collection_name

        if not self._client.collection_exists(collection_name):
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.config.embeddings.dimensions,
                    distance=Distance.COSINE,
                ),
            )

    def _generate_id(self, content: str, source: str) -> str:
        """Generate deterministic ID from content and source.

        This allows idempotent upserts - same content+source = same ID.
        Uses UUID format as required by qdrant-client 1.9+.

        Args:
            content: The knowledge content
            source: Source of the content

        Returns:
            Deterministic UUID-formatted ID
        """
        import uuid

        hash_input = f"{content}|{source}"
        # Take first 32 hex chars to create a valid UUID
        hex_digest = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
        return str(uuid.UUID(hex_digest))

    async def store(
        self,
        content: str,
        type: str,
        tags: list[str],
        source: str,
        file_paths: list[str] | None,
        embedding: list[float],
    ) -> str:
        """Store a knowledge entry in Qdrant.

        Uses deterministic ID generation for idempotent upserts.

        Args:
            content: The knowledge content
            type: Knowledge type (bug, feature, etc.)
            tags: List of tags
            source: Source of the content (github, slack, etc.)
            file_paths: Related file paths (optional)
            embedding: Pre-computed embedding vector

        Returns:
            The point ID
        """
        point_id = self._generate_id(content, source)

        payload = {
            "content": content,
            "type": type,
            "tags": tags,
            "source": source,
            "file_paths": file_paths,
            "created_at": datetime.now(UTC).isoformat(),
        }

        self._client.upsert(
            collection_name=self.config.qdrant.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )

        return point_id

    async def search(
        self,
        embedding: list[float],
        type_filter: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search for similar knowledge entries.

        Args:
            embedding: Query embedding vector
            type_filter: Optional type to filter by
            limit: Maximum results to return

        Returns:
            List of matching entries with scores
        """
        query_filter = None
        if type_filter:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="type",
                        match=MatchValue(value=type_filter),
                    )
                ]
            )

        # Use query_points (qdrant-client 1.9+ API)
        response = self._client.query_points(
            collection_name=self.config.qdrant.collection_name,
            query=embedding,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                **hit.payload,
            }
            for hit in response.points
        ]

    async def find_duplicates(
        self,
        embedding: list[float],
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Find potential duplicates based on similarity.

        Args:
            embedding: Embedding of content to check
            threshold: Similarity threshold (default from config)

        Returns:
            List of similar entries above threshold
        """
        if threshold is None:
            threshold = self.config.thresholds.duplicate_similarity

        # Search for similar items (qdrant-client 1.9+ API)
        response = self._client.query_points(
            collection_name=self.config.qdrant.collection_name,
            query=embedding,
            limit=5,  # Only check top 5 for duplicates
        )

        duplicates = []
        for hit in response.points:
            if hit.score >= threshold:
                duplicates.append(
                    {
                        "id": hit.id,
                        "similarity_score": hit.score,
                        "content_preview": hit.payload.get("content", "")[:100],
                        **hit.payload,
                    }
                )

        return duplicates

    async def get_by_file_path(self, file_path: str) -> list[dict[str, Any]]:
        """Get knowledge entries related to a file path.

        Args:
            file_path: Path to the file

        Returns:
            List of entries referencing this file
        """
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="file_paths",
                    match=MatchValue(value=file_path),
                )
            ]
        )

        results, _ = self._client.scroll(
            collection_name=self.config.qdrant.collection_name,
            scroll_filter=scroll_filter,
            limit=50,
        )

        return [
            {
                "id": point.id,
                **point.payload,
            }
            for point in results
        ]

    async def get_embedding(self, content: str) -> list[float]:
        """Generate embedding for content using FastEmbed (runs locally).

        FastEmbed uses ONNX Runtime to run the model on your CPU.
        No API calls are made - everything happens locally.

        Args:
            content: Text to embed

        Returns:
            Embedding vector (384 dimensions for bge-small-en-v1.5)
        """
        # FastEmbed.embed() returns a generator, we need to convert to list
        embeddings = list(self._embedder.embed([content]))
        return embeddings[0].tolist()

    async def delete(self, point_id: str) -> None:
        """Delete a knowledge entry by ID.

        Args:
            point_id: ID of the entry to delete
        """
        self._client.delete(
            collection_name=self.config.qdrant.collection_name,
            points_selector=[point_id],
        )
