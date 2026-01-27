"""Shared test fixtures for PendoMind."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np


@pytest.fixture
def mock_embedding():
    """Mock FastEmbed embedding vector (384 dimensions for bge-small-en-v1.5)."""
    return [0.1] * 384


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path for testing."""
    return tmp_path / "test_memory.db"


@pytest.fixture
def sample_memory_content():
    """Sample high-quality memory content."""
    return "Python's GIL (Global Interpreter Lock) only affects CPU-bound threads. IO-bound operations release the GIL, allowing true concurrency for network and file operations."


@pytest.fixture
def sample_fact_content():
    """Sample fact content."""
    return "The authentication service uses JWT tokens with a 1-hour expiry and refresh tokens with 7-day expiry."


@pytest.fixture
def sample_learning_content():
    """Sample learning content."""
    return "When debugging database connection issues, always check connection pool settings first. Most production issues stem from pool exhaustion under load."
