"""Quality control middleware for PendoMind knowledge storage."""

from dataclasses import dataclass
from typing import Any

from pendomind.config import PendoMindConfig
from pendomind.knowledge import KnowledgeBase
from pendomind.quality import QualityScorer
from pendomind.tools import PendingItem, PendingStore


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    error: str | None = None


class QualityMiddleware:
    """Middleware for quality control of knowledge storage.

    Performs validation and quality-based routing:
    - Type validation (must be in allowed list)
    - Content validation (no excluded patterns like passwords)
    - Length validation (within min/max limits)
    - Quality scoring with three-tier routing
    - Duplicate detection
    """

    def __init__(self, config: PendoMindConfig | None = None):
        """Initialize middleware with configuration.

        Args:
            config: PendoMindConfig for validation rules
        """
        self.config = config or PendoMindConfig()

        # These can be injected for testing
        self.scorer: QualityScorer | None = None
        self.kb: KnowledgeBase | None = None
        self.pending_store: PendingStore | None = None

    def validate_type(self, type_name: str) -> ValidationResult:
        """Validate that the knowledge type is allowed.

        Args:
            type_name: The type to validate

        Returns:
            ValidationResult indicating pass/fail
        """
        if type_name in self.config.types.allowed:
            return ValidationResult(is_valid=True)
        return ValidationResult(
            is_valid=False,
            error=f"Invalid type '{type_name}'. Allowed types: {self.config.types.allowed}",
        )

    def validate_content(self, content: str) -> ValidationResult:
        """Validate content doesn't contain excluded patterns.

        Args:
            content: The content to validate

        Returns:
            ValidationResult indicating pass/fail
        """
        content_lower = content.lower()
        for pattern in self.config.filtering.excluded_patterns:
            if pattern.lower() in content_lower:
                return ValidationResult(
                    is_valid=False,
                    error=f"Content contains excluded pattern: '{pattern}'",
                )
        return ValidationResult(is_valid=True)

    def validate_length(self, content: str) -> ValidationResult:
        """Validate content length is within limits.

        Args:
            content: The content to validate

        Returns:
            ValidationResult indicating pass/fail
        """
        word_count = len(content.split())

        if word_count < self.config.filtering.min_content_length:
            return ValidationResult(
                is_valid=False,
                error=f"Content too short ({word_count} words). Minimum: {self.config.filtering.min_content_length}",
            )

        if word_count > self.config.filtering.max_content_length:
            return ValidationResult(
                is_valid=False,
                error=f"Content too long ({word_count} words). Maximum: {self.config.filtering.max_content_length}",
            )

        return ValidationResult(is_valid=True)

    async def process(
        self,
        content: str,
        type: str,
        tags: list[str],
        source: str,
        file_paths: list[str] | None,
    ) -> dict[str, Any]:
        """Process a knowledge storage request with quality control.

        Validates content and routes based on quality score:
        - Score < 0.65: Auto-reject
        - Score 0.65-0.85: Pending (requires confirmation)
        - Score > 0.85: Auto-approve

        Args:
            content: The knowledge content
            type: Knowledge type (bug, feature, etc.)
            tags: List of tags
            source: Source of the content
            file_paths: Related file paths

        Returns:
            Dict with status and details
        """
        # Step 1: Validate type
        type_result = self.validate_type(type)
        if not type_result.is_valid:
            return {"status": "rejected", "message": type_result.error}

        # Step 2: Validate content patterns
        content_result = self.validate_content(content)
        if not content_result.is_valid:
            return {"status": "rejected", "message": content_result.error}

        # Step 3: Validate length
        length_result = self.validate_length(content)
        if not length_result.is_valid:
            return {"status": "rejected", "message": length_result.error}

        # Initialize dependencies if not injected
        if self.scorer is None:
            self.scorer = QualityScorer(self.config)
        if self.kb is None:
            self.kb = KnowledgeBase(self.config)
        if self.pending_store is None:
            self.pending_store = PendingStore(config=self.config)

        # Step 4: Get embedding and check duplicates
        embedding = await self.kb.get_embedding(content)
        duplicates = await self.kb.find_duplicates(embedding)

        # Step 5: Calculate quality score
        quality_analysis = await self.scorer.score(content, type, source)
        quality_score = quality_analysis.composite_score

        # Step 6: Route based on quality score
        min_threshold = self.config.get_min_score_for_type(type)
        auto_approve_threshold = self.config.thresholds.auto_approve_score

        if quality_score < min_threshold:
            # Auto-reject
            return {
                "status": "rejected",
                "message": f"Quality score {quality_score:.2f} below threshold {min_threshold:.2f}",
                "quality_score": quality_score,
                "quality_analysis": {
                    "relevance": quality_analysis.relevance_score,
                    "completeness": quality_analysis.completeness_score,
                    "credibility": quality_analysis.credibility_score,
                },
                "recommendations": quality_analysis.recommendations,
            }

        if quality_score >= auto_approve_threshold:
            # Auto-approve and store
            point_id = await self.kb.store(
                content=content,
                type=type,
                tags=tags,
                source=source,
                file_paths=file_paths,
                embedding=embedding,
            )
            return {
                "status": "stored",
                "id": point_id,
                "quality_score": quality_score,
                "duplicates": duplicates if duplicates else None,
            }

        # Pending - requires confirmation
        pending_item = PendingItem(
            id="",  # Will be generated
            content=content,
            type=type,
            tags=tags,
            source=source,
            file_paths=file_paths,
            embedding=embedding,
            quality_analysis=quality_analysis,
            duplicate_info=duplicates[0] if duplicates else None,
        )
        pending_id = self.pending_store.add(pending_item)

        return {
            "status": "pending",
            "pending_id": pending_id,
            "quality_score": quality_score,
            "quality_analysis": {
                "relevance": quality_analysis.relevance_score,
                "completeness": quality_analysis.completeness_score,
                "credibility": quality_analysis.credibility_score,
            },
            "recommendations": quality_analysis.recommendations,
            "duplicates": duplicates if duplicates else None,
        }
