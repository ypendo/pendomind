"""Configuration for PendoMind.

Minimal configuration - most settings have sensible defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EmbeddingsConfig:
    """Embedding configuration for FastEmbed.

    FastEmbed runs locally using ONNX Runtime - no API keys needed.
    Model is downloaded once from HuggingFace Hub, then cached locally.
    """

    model: str = "BAAI/bge-small-en-v1.5"
    dimensions: int = 384


@dataclass
class PendoMindConfig:
    """Main configuration for PendoMind.

    Most users won't need to change these - just use defaults.
    """

    # Database path (default: ~/.pendomind/memory.db)
    db_path: Path = field(default_factory=lambda: Path.home() / ".pendomind" / "memory.db")

    # Embedding settings
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)

    # Similarity threshold for auto-deduplication (0.0 - 1.0)
    duplicate_threshold: float = 0.90

    @classmethod
    def default(cls) -> "PendoMindConfig":
        """Get default configuration."""
        return cls()
