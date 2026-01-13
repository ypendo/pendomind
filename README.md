# PendoMind

An engineering knowledge base with MCP integration and built-in **data quality control**.

## Features

- **Semantic Search** - Find past work using natural language queries
- **Quality Control** - Three-tier system prevents garbage from polluting the knowledge base
- **100% Free & Local** - Uses FastEmbed for embeddings, no API keys required
- **MCP Integration** - Works seamlessly with Claude Code

## Tech Stack

| Component  | Technology |
| ---------- | ---------- |
| Vector DB  | Qdrant (Docker) |
| Framework  | FastMCP (Python) |
| Embeddings | FastEmbed (local, free) |

## Quick Start

```bash
# 1. Start Qdrant
docker run -d -p 6333:6333 --name pendomind-qdrant qdrant/qdrant

# 2. Install PendoMind
pip install -e .

# 3. Run MCP server (no API keys needed!)
python -m pendomind.main
```

> **Note**: First run downloads the embedding model (~130MB). After that, everything runs locally!

## Claude Code Config

Add to your MCP settings (`~/.claude.json`):

```json
{
  "mcpServers": {
    "pendomind": {
      "command": "python",
      "args": ["-m", "pendomind.main"],
      "cwd": "/path/to/pendomind"
    }
  }
}
```

## MCP Tools

| Tool | Description |
| ---- | ----------- |
| `search_knowledge(query)` | Semantic search across all knowledge |
| `remember_knowledge(content, type, tags)` | Store with quality control |
| `confirm_knowledge(pending_id, approved)` | Confirm/reject pending entries |
| `recall_context(query)` | Get formatted context for prompts |
| `find_similar(content)` | Check for duplicates before storing |
| `get_file_context(file_path)` | Get knowledge related to a file |

## Quality Control

Content goes through three tiers:

| Score | Action |
| ----- | ------ |
| < 0.65 | Auto-reject |
| 0.65 - 0.85 | Pending (user confirmation required) |
| > 0.85 | Auto-store |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=pendomind --cov-report=term-missing
```

## Documentation

See [docs/PENDOMIND_PLAN.md](docs/PENDOMIND_PLAN.md) for full architecture and design details.

## License

MIT
