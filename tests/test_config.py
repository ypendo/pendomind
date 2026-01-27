"""Tests for PendoMind configuration."""

import pytest
from pathlib import Path


class TestPendoMindConfig:
    """Test the simplified configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.db_path == Path.home() / ".pendomind" / "memory.db"
        assert config.duplicate_threshold == 0.90
        assert config.embeddings.model == "BAAI/bge-small-en-v1.5"
        assert config.embeddings.dimensions == 384

    def test_default_classmethod(self):
        """default() should return a default config."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig.default()

        assert config.db_path == Path.home() / ".pendomind" / "memory.db"

    def test_custom_db_path(self):
        """Should accept custom db_path."""
        from pendomind.config import PendoMindConfig

        custom_path = Path("/custom/path/memory.db")
        config = PendoMindConfig(db_path=custom_path)

        assert config.db_path == custom_path


class TestEmbeddingsConfig:
    """Test embeddings configuration."""

    def test_default_embeddings_config(self):
        """Should have correct FastEmbed defaults."""
        from pendomind.config import EmbeddingsConfig

        config = EmbeddingsConfig()

        assert config.model == "BAAI/bge-small-en-v1.5"
        assert config.dimensions == 384

    def test_custom_embeddings_model(self):
        """Should accept custom model name."""
        from pendomind.config import EmbeddingsConfig

        config = EmbeddingsConfig(model="custom/model", dimensions=768)

        assert config.model == "custom/model"
        assert config.dimensions == 768
