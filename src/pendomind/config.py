"""Configuration management for PendoMind."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ThresholdsConfig:
    """Quality score thresholds configuration."""

    min_quality_score: float = 0.65
    auto_approve_score: float = 0.85
    duplicate_similarity: float = 0.90


@dataclass
class PendingConfig:
    """Pending item configuration."""

    ttl_minutes: int = 30
    cleanup_interval_seconds: int = 60


@dataclass
class TypesConfig:
    """Knowledge types configuration."""

    allowed: list[str] = field(
        default_factory=lambda: [
            "bug",
            "feature",
            "incident",
            "debugging",
            "architecture",
            "error",
            "investigation",
        ]
    )
    overrides: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class FilteringConfig:
    """Content filtering configuration."""

    excluded_patterns: list[str] = field(
        default_factory=lambda: [
            "password",
            "api_key",
            "api-key",
            "secret",
            "token",
            "credential",
            "private_key",
            "private-key",
        ]
    )
    min_content_length: int = 15
    max_content_length: int = 5000


@dataclass
class SourcesConfig:
    """Source credibility configuration."""

    credibility: dict[str, float] = field(
        default_factory=lambda: {
            "github": 0.95,
            "confluence": 0.85,
            "jira": 0.80,
            "claude_session": 0.70,
            "slack": 0.60,
        }
    )


@dataclass
class QdrantConfig:
    """Qdrant connection configuration."""

    host: str = "localhost"
    port: int = 6333
    collection_name: str = "pendomind_knowledge"


@dataclass
class ScoringConfig:
    """Quality scoring configuration."""

    weights: dict[str, float] = field(
        default_factory=lambda: {
            "relevance": 0.40,
            "completeness": 0.35,
            "credibility": 0.25,
        }
    )
    domain_keywords: dict[str, list[str]] = field(
        default_factory=lambda: {
            "high_relevance": [
                "bug",
                "fix",
                "error",
                "exception",
                "stack trace",
                "implementation",
                "feature",
                "refactor",
                "optimization",
                "incident",
                "outage",
                "RCA",
                "root cause",
                "architecture",
                "design",
                "pattern",
                "service",
            ],
            "medium_relevance": [
                "configuration",
                "deploy",
                "test",
                "review",
                "documentation",
                "setup",
                "migration",
            ],
        }
    )


@dataclass
class EmbeddingsConfig:
    """Embedding configuration for FastEmbed.

    FastEmbed runs locally using ONNX Runtime - no API keys needed.
    Model is downloaded once from HuggingFace Hub, then cached locally.
    """

    model: str = "BAAI/bge-small-en-v1.5"
    dimensions: int = 384
    batch_size: int = 100


@dataclass
class PendoMindConfig:
    """Main configuration for PendoMind."""

    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    pending: PendingConfig = field(default_factory=PendingConfig)
    types: TypesConfig = field(default_factory=TypesConfig)
    filtering: FilteringConfig = field(default_factory=FilteringConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)

    @classmethod
    def load(cls, path: Path | str = "config/quality_rules.yaml") -> "PendoMindConfig":
        """Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            PendoMindConfig with loaded values, defaults for missing
        """
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "PendoMindConfig":
        """Create config from dictionary."""
        return cls(
            thresholds=cls._load_thresholds(data.get("thresholds", {})),
            pending=cls._load_pending(data.get("pending", {})),
            types=cls._load_types(data.get("types", {})),
            filtering=cls._load_filtering(data.get("filtering", {})),
            sources=cls._load_sources(data.get("sources", {})),
            qdrant=cls._load_qdrant(data.get("qdrant", {})),
            scoring=cls._load_scoring(data.get("scoring", {})),
            embeddings=cls._load_embeddings(data.get("embeddings", {})),
        )

    @staticmethod
    def _load_thresholds(data: dict) -> ThresholdsConfig:
        """Load thresholds config."""
        defaults = ThresholdsConfig()
        return ThresholdsConfig(
            min_quality_score=data.get("min_quality_score", defaults.min_quality_score),
            auto_approve_score=data.get(
                "auto_approve_score", defaults.auto_approve_score
            ),
            duplicate_similarity=data.get(
                "duplicate_similarity", defaults.duplicate_similarity
            ),
        )

    @staticmethod
    def _load_pending(data: dict) -> PendingConfig:
        """Load pending config."""
        defaults = PendingConfig()
        return PendingConfig(
            ttl_minutes=data.get("ttl_minutes", defaults.ttl_minutes),
            cleanup_interval_seconds=data.get(
                "cleanup_interval_seconds", defaults.cleanup_interval_seconds
            ),
        )

    @staticmethod
    def _load_types(data: dict) -> TypesConfig:
        """Load types config."""
        defaults = TypesConfig()
        return TypesConfig(
            allowed=data.get("allowed", defaults.allowed),
            overrides=data.get("overrides", defaults.overrides),
        )

    @staticmethod
    def _load_filtering(data: dict) -> FilteringConfig:
        """Load filtering config."""
        defaults = FilteringConfig()
        return FilteringConfig(
            excluded_patterns=data.get(
                "excluded_patterns", defaults.excluded_patterns
            ),
            min_content_length=data.get(
                "min_content_length", defaults.min_content_length
            ),
            max_content_length=data.get(
                "max_content_length", defaults.max_content_length
            ),
        )

    @staticmethod
    def _load_sources(data: dict) -> SourcesConfig:
        """Load sources config."""
        defaults = SourcesConfig()
        return SourcesConfig(
            credibility=data.get("credibility", defaults.credibility),
        )

    @staticmethod
    def _load_qdrant(data: dict) -> QdrantConfig:
        """Load Qdrant config."""
        defaults = QdrantConfig()
        return QdrantConfig(
            host=data.get("host", defaults.host),
            port=data.get("port", defaults.port),
            collection_name=data.get("collection_name", defaults.collection_name),
        )

    @staticmethod
    def _load_scoring(data: dict) -> ScoringConfig:
        """Load scoring config."""
        defaults = ScoringConfig()
        return ScoringConfig(
            weights=data.get("weights", defaults.weights),
            domain_keywords=data.get("domain_keywords", defaults.domain_keywords),
        )

    @staticmethod
    def _load_embeddings(data: dict) -> EmbeddingsConfig:
        """Load embeddings config."""
        defaults = EmbeddingsConfig()
        return EmbeddingsConfig(
            model=data.get("model", defaults.model),
            dimensions=data.get("dimensions", defaults.dimensions),
            batch_size=data.get("batch_size", defaults.batch_size),
        )

    def get_min_score_for_type(self, type_name: str) -> float:
        """Get minimum quality score for a specific type.

        Args:
            type_name: Knowledge type (bug, feature, etc.)

        Returns:
            Minimum score threshold, using type override if defined
        """
        if type_name in self.types.overrides:
            override = self.types.overrides[type_name]
            if "min_quality_score" in override:
                return override["min_quality_score"]
        return self.thresholds.min_quality_score

    def get_source_credibility(self, source: str) -> float:
        """Get credibility score for a source.

        Args:
            source: Source name (github, confluence, etc.)

        Returns:
            Credibility score, defaulting to 0.50 for unknown sources
        """
        return self.sources.credibility.get(source, 0.50)
