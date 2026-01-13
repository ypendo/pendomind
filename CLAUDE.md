# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is PendoMind?

An MCP server that provides a persistent engineering knowledge base. It stores bug fixes, debugging sessions, feature implementations, and investigations with quality control to prevent garbage data.

## Python Environment

**Always use the project's virtual environment:**

```bash
# Activate before running any commands
source ~/.pyenv/versions/3.12.2/envs/pendomind/bin/activate

# Or use the full path directly
~/.pyenv/versions/3.12.2/envs/pendomind/bin/python
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest
```

The virtual environment is located at: `~/.pyenv/versions/3.12.2/envs/pendomind`

## Commands

All commands assume the virtual environment is activated or use full paths.

```bash
# Run all tests
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/ -v

# Run with coverage
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/ -v --cov=pendomind --cov-report=term-missing

# Run a single test file
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/test_quality.py -v

# Run a single test
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/test_quality.py::TestRelevanceScoring::test_high_relevance_bug_with_stack_trace -v

# Start Qdrant (required for runtime)
docker run -d -p 6333:6333 --name pendomind-qdrant qdrant/qdrant

# Run the MCP server
~/.pyenv/versions/3.12.2/envs/pendomind/bin/python -m pendomind.main

# Install for development
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pip install -e ".[dev]"
```

## Architecture

```
Claude Code ──stdio──▶ FastMCP Server ──▶ Qdrant (Docker)
                       │                   localhost:6333
                       │
                       ├── QualityMiddleware
                       ├── QualityScorer
                       ├── PendingStore
                       └── KnowledgeBase
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `main.py` | FastMCP server entry point, registers all 7 MCP tools |
| `knowledge.py` | Qdrant wrapper: store, search, find_duplicates, get_by_file_path |
| `middleware.py` | Quality control: validates content, routes to approve/reject/pending |
| `quality.py` | Scoring: relevance (keywords), completeness (structure), credibility (source) |
| `tools.py` | MCP tool implementations + PendingStore for user confirmation workflow |
| `config.py` | Loads `config/quality_rules.yaml`, provides typed config dataclasses |

### Quality Control Flow

```
remember_knowledge() → QualityMiddleware.process()
                           │
                           ├── validate_type()      → reject if invalid type
                           ├── validate_content()   → reject if contains secrets
                           ├── validate_length()    → reject if too short/long
                           ├── QualityScorer.score() → calculate 0-1 score
                           │
                           └── Route by score:
                               < 0.65  → auto-reject
                               > 0.85  → auto-approve → KnowledgeBase.store()
                               else    → pending → PendingStore.add()
```

### Embedding Model

Uses **FastEmbed** with `BAAI/bge-small-en-v1.5` (384 dimensions). Runs locally - no API keys needed. Model cached in `~/.cache/fastembed/` after first download (~130MB).

## Testing

All tests mock external dependencies (Qdrant, FastEmbed). See `tests/conftest.py` for shared fixtures.

```python
# Pattern for mocking FastEmbed in tests
with patch("pendomind.knowledge.TextEmbedding") as mock_fastembed:
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
    mock_fastembed.return_value = mock_embedder
```

## Knowledge Types

7 types with configurable quality thresholds in `config/quality_rules.yaml`:
- `bug`, `feature`, `debugging`, `error` → threshold 0.65
- `incident`, `investigation` → threshold 0.60 (lenient)
- `architecture` → threshold 0.75 (strict)

## MCP Tools (7 total)

| Tool | Purpose |
|------|---------|
| `search_knowledge` | Semantic search |
| `remember_knowledge` | Store with quality control |
| `confirm_knowledge` | Confirm/reject pending entries |
| `recall_context` | Get formatted context |
| `find_similar` | Check for duplicates |
| `get_file_context` | Get file-related knowledge |
| `list_pending` | List pending entries |
