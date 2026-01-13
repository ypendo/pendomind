"""Shared test fixtures for PendoMind."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def sample_bug_content():
    """Sample high-quality bug content."""
    return """
    Bug: NullPointerException in UserService.getUser()

    Problem: Users receiving 500 errors when accessing profile page

    Context: Production environment, affects ~5% of requests

    Root Cause: Race condition in user cache invalidation

    Solution: Added synchronization to cache update

    ```python
    with self._lock:
        self._cache[user_id] = user
    ```

    Verified fix reduced error rate to 0%.
    """


@pytest.fixture
def sample_medium_quality_content():
    """Sample medium-quality content (0.65-0.85 range)."""
    return """
    Fixed a bug in the user service where users couldn't log in.
    The problem was in the authentication flow.
    Updated the code to handle edge cases properly.
    """


@pytest.fixture
def sample_low_quality_content():
    """Sample low-quality content (< 0.65)."""
    return "Fixed bug"


@pytest.fixture
def sample_incident_content():
    """Sample incident report content."""
    return """
    Incident: Production outage in aggregation service

    Timeline:
    - 14:00 UTC: Alerts fired for high error rate
    - 14:05 UTC: On-call engineer paged
    - 14:15 UTC: Root cause identified - database connection pool exhausted
    - 14:20 UTC: Increased pool size, service recovering
    - 14:30 UTC: All green, incident resolved

    Root Cause Analysis:
    The connection pool was sized for normal traffic but couldn't handle
    the spike from a marketing campaign launch.

    Action Items:
    1. Increase default pool size from 10 to 50
    2. Add alerting for connection pool utilization
    3. Document scaling procedures
    """


@pytest.fixture
def mock_embedding():
    """Mock FastEmbed embedding vector (384 dimensions for bge-small-en-v1.5)."""
    return [0.1] * 384


@pytest.fixture
def temp_config_file(tmp_path):
    """Temporary config file for testing."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
thresholds:
  min_quality_score: 0.65
  auto_approve_score: 0.85
  duplicate_similarity: 0.90

pending:
  ttl_minutes: 30

types:
  allowed:
    - bug
    - feature
    - incident
    - debugging
    - architecture
    - error

filtering:
  excluded_patterns:
    - password
    - api_key
    - secret
    - token
  min_content_length: 15
  max_content_length: 5000

sources:
  credibility:
    github: 0.95
    confluence: 0.85
    jira: 0.80
    claude_session: 0.70
    slack: 0.60
""")
    return config_path


@pytest.fixture
def mock_quality_analysis():
    """Mock QualityAnalysis object."""
    analysis = MagicMock()
    analysis.relevance_score = 0.75
    analysis.completeness_score = 0.70
    analysis.credibility_score = 0.80
    analysis.composite_score = 0.74
    analysis.relevance_details = "Found domain keywords"
    analysis.completeness_details = "Has problem and solution"
    analysis.recommendations = ["Consider adding more context"]
    return analysis


@pytest.fixture
def mock_duplicate_info():
    """Mock DuplicateInfo object."""
    info = MagicMock()
    info.has_duplicates = False
    info.duplicates = []
    info.recommendation = "store"
    return info
