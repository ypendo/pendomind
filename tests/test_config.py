"""Tests for PendoMind configuration module."""

import pytest
from pathlib import Path


class TestConfigLoading:
    """Test configuration file loading."""

    def test_load_default_config_when_file_missing(self, tmp_path):
        """When config file doesn't exist, use defaults."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig.load(tmp_path / "nonexistent.yaml")

        assert config.thresholds.min_quality_score == 0.65
        assert config.thresholds.auto_approve_score == 0.85
        assert config.thresholds.duplicate_similarity == 0.90

    def test_load_yaml_config(self, tmp_path):
        """Load configuration from YAML file."""
        from pendomind.config import PendoMindConfig

        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
thresholds:
  min_quality_score: 0.70
  auto_approve_score: 0.90
""")
        config = PendoMindConfig.load(config_file)

        assert config.thresholds.min_quality_score == 0.70
        assert config.thresholds.auto_approve_score == 0.90
        # Should keep default for unspecified
        assert config.thresholds.duplicate_similarity == 0.90

    def test_load_from_project_config(self, temp_config_file):
        """Load configuration from project config file."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig.load(temp_config_file)

        assert config.thresholds.min_quality_score == 0.65
        assert "bug" in config.types.allowed
        assert "password" in config.filtering.excluded_patterns


class TestThresholdsConfig:
    """Test threshold configuration."""

    def test_default_thresholds(self):
        """Default thresholds should be sensible."""
        from pendomind.config import ThresholdsConfig

        thresholds = ThresholdsConfig()

        assert thresholds.min_quality_score == 0.65
        assert thresholds.auto_approve_score == 0.85
        assert thresholds.duplicate_similarity == 0.90

    def test_thresholds_from_dict(self):
        """Create thresholds from dictionary."""
        from pendomind.config import ThresholdsConfig

        thresholds = ThresholdsConfig(
            min_quality_score=0.70,
            auto_approve_score=0.90,
            duplicate_similarity=0.95
        )

        assert thresholds.min_quality_score == 0.70
        assert thresholds.auto_approve_score == 0.90
        assert thresholds.duplicate_similarity == 0.95


class TestTypesConfig:
    """Test knowledge types configuration."""

    def test_default_allowed_types(self):
        """Default should include all standard types."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        expected_types = ["bug", "feature", "incident", "debugging", "architecture", "error"]
        for t in expected_types:
            assert t in config.types.allowed

    def test_get_min_score_for_type_default(self):
        """Default min score when no type override."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.get_min_score_for_type("bug") == 0.65
        assert config.get_min_score_for_type("feature") == 0.65

    def test_get_min_score_for_type_with_override(self):
        """Type-specific override for min score."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()
        config.types.overrides = {"incident": {"min_quality_score": 0.60}}

        assert config.get_min_score_for_type("incident") == 0.60
        assert config.get_min_score_for_type("bug") == 0.65  # Still default


class TestFilteringConfig:
    """Test filtering configuration."""

    def test_default_excluded_patterns(self):
        """Default patterns should include security-sensitive terms."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert "password" in config.filtering.excluded_patterns
        assert "api_key" in config.filtering.excluded_patterns
        assert "secret" in config.filtering.excluded_patterns
        assert "token" in config.filtering.excluded_patterns

    def test_default_content_length_limits(self):
        """Default content length limits should be reasonable."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.filtering.min_content_length == 15
        assert config.filtering.max_content_length == 5000


class TestSourcesConfig:
    """Test source credibility configuration."""

    def test_default_source_credibility(self):
        """Default source credibility weights."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.sources.credibility.get("github") == 0.95
        assert config.sources.credibility.get("confluence") == 0.85
        assert config.sources.credibility.get("slack") == 0.60

    def test_get_source_credibility_default(self):
        """Unknown source should return default credibility."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        # Unknown source should return 0.50
        assert config.get_source_credibility("unknown_source") == 0.50
        assert config.get_source_credibility("github") == 0.95


class TestQdrantConfig:
    """Test Qdrant configuration."""

    def test_default_qdrant_settings(self):
        """Default Qdrant connection settings."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.qdrant.host == "localhost"
        assert config.qdrant.port == 6333
        assert config.qdrant.collection_name == "pendomind_knowledge"


class TestScoringConfig:
    """Test quality scoring configuration."""

    def test_default_scoring_weights(self):
        """Default scoring weights should sum to 1.0."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        total = (
            config.scoring.weights.get("relevance", 0) +
            config.scoring.weights.get("completeness", 0) +
            config.scoring.weights.get("credibility", 0)
        )
        assert abs(total - 1.0) < 0.01  # Allow small floating point error

    def test_default_scoring_weights_values(self):
        """Default scoring weight values."""
        from pendomind.config import PendoMindConfig

        config = PendoMindConfig()

        assert config.scoring.weights.get("relevance") == 0.40
        assert config.scoring.weights.get("completeness") == 0.35
        assert config.scoring.weights.get("credibility") == 0.25
