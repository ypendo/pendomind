# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is PendoMind?

A simple memory persistence layer for Claude. Stores facts, notes, and learnings with semantic search powered by SQLite + sqlite-vec. No Docker required - just works.

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

```bash
# Run all tests
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/ -v

# Run with coverage
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/ -v --cov=pendomind --cov-report=term-missing

# Run a single test file
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pytest tests/test_memory.py -v

# Run the MCP server
~/.pyenv/versions/3.12.2/envs/pendomind/bin/python -m pendomind.main

# Install for development
~/.pyenv/versions/3.12.2/envs/pendomind/bin/pip install -e ".[dev]"
```

## Architecture

```
Claude Code ──stdio──▶ FastMCP Server ──▶ SQLite + sqlite-vec
                       │                   ~/.pendomind/memory.db
                       │
                       └── MemoryStore
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `main.py` | FastMCP server entry point, registers 6 simple MCP tools |
| `memory.py` | SQLite + sqlite-vec backend: store, search, delete, list |
| `config.py` | Minimal config: db_path, embedding settings |

### Embedding Model

Uses **FastEmbed** with `BAAI/bge-small-en-v1.5` (384 dimensions). Runs locally - no API keys needed. Model cached in `~/.cache/fastembed/` after first download (~130MB).

### Database

Uses **sqlite-vec** for vector similarity search, loaded via **APSW** (for macOS extension support). Database stored at `~/.pendomind/memory.db`.

Tables:
- `memories` - Main metadata (id, content, type, tags, timestamps)
- `memories_vec` - Vector embeddings (sqlite-vec virtual table)
- `memory_vectors` - Mapping between memory IDs and vector rowids

## Testing

Tests mock FastEmbed. See `tests/conftest.py` for shared fixtures.

```python
# Pattern for mocking FastEmbed in tests
with patch("pendomind.memory.TextEmbedding") as mock_fastembed:
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = iter([np.array([0.1] * 384)])
    mock_fastembed.return_value = mock_embedder
```

## Memory Types

3 simple types:
- `fact` - Verified information, solutions, configs
- `note` - Observations, ideas, WIP thoughts (default)
- `learning` - Lessons learned, insights, patterns

## MCP Tools (6 total)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `remember` | Store a memory | `content`, `tags?`, `type?` |
| `search` | Semantic search | `query`, `limit?`, `type?` |
| `forget` | Delete by ID | `id` |
| `list_memories` | List all memories | `limit?`, `type?` |
| `recall` | Get context for prompts | `query`, `limit?` |
| `similar` | Find duplicates | `content` |

## Example Usage

```python
# Store a memory
remember("Python's GIL only affects CPU-bound threads", tags=["python"])

# Search semantically
search("python threading")

# List all memories
list_memories()

# Delete a memory
forget("abc123-def456")
```
