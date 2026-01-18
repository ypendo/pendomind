# PendoMind

**Persistent memory layer for Pendo's AI coding assistants.**

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

---

## Usage Guide

### When to Use PendoMind

| Scenario | What to Say to Claude Code |
|----------|----------------------------|
| **Fixed a bug** | "Remember this bug fix: [description of problem, cause, and solution]" |
| **Investigating code** | "Remember this investigation: [what you discovered]" |
| **Starting new feature** | "Search pendomind for similar implementations of X" |
| **Debugging an error** | "Search pendomind for errors like [error message]" |
| **On-call incident** | "Find past incidents with [service name]" |
| **Before editing a file** | "What do we know about [file path]?" |

### Example Prompts

```
# Store a bug fix
"Remember this bug fix: The aggregation service was timing out because
the connection pool was exhausted. Root cause was missing connection
release in error paths. Fixed by adding defer conn.Close() in handler."

# Search for past knowledge
"Search pendomind for authentication bugs"
"Find incidents related to Redis"
"Search for how we implemented caching"

# Get file context before editing
"What do we know about src/api/handlers.py?"
"Get context for the aggregation service"

# Check for duplicates before storing
"Check if we already have knowledge about Redis connection timeouts"

# Store an investigation
"Remember this investigation: While debugging the slow API response,
I discovered that the service makes 3 sequential database calls that
could be parallelized. The queries are in src/db/queries.go lines 45-67."
```

### Common Workflows

**Bug Fix Workflow:**
1. Search for similar bugs: *"Have we seen this error before?"*
2. Fix the bug
3. Store the knowledge: *"Remember this bug fix: [problem, cause, solution]"*

**Investigation Workflow:**
1. Store discoveries as you go: *"Remember this investigation: [findings]"*
2. Include file paths for context
3. Lower quality threshold (0.60) allows partial findings

**Feature Development Workflow:**
1. Search for similar implementations: *"How did we implement X?"*
2. Get file context: *"What do we know about this module?"*
3. After completing: *"Remember this feature: [what was built and design decisions]"*

---

## MCP Tools

| Tool | Description |
| ---- | ----------- |
| `search_knowledge(query, type_filter?, limit?)` | Semantic search across all knowledge |
| `remember_knowledge(content, type, tags, source?, file_paths?)` | Store with quality control |
| `confirm_knowledge(pending_id, approved)` | Confirm/reject pending entries |
| `recall_context(query, type_filter?, limit?)` | Get formatted context for prompts |
| `find_similar(content)` | Check for duplicates before storing |
| `get_file_context(file_path)` | Get knowledge related to a file |
| `list_pending()` | List all pending entries awaiting confirmation |

## Knowledge Types

| Type | Description | Quality Threshold |
| ---- | ----------- | ----------------- |
| `bug` | Bug reports, root causes, and fixes | 0.65 |
| `feature` | Feature implementations, design decisions | 0.65 |
| `incident` | Incident reports, RCAs, resolutions | 0.60 (lenient) |
| `debugging` | Debugging sessions, symptoms, solutions | 0.65 |
| `architecture` | System design, service dependencies | 0.75 (strict) |
| `error` | Error patterns and their fixes | 0.65 |
| `investigation` | Exploratory discoveries during code exploration | 0.60 (lenient) |

## Quality Control

Content goes through three tiers:

| Score | Action |
| ----- | ------ |
| < 0.65 | Auto-reject (with recommendations) |
| 0.65 - 0.85 | Pending (user confirmation required) |
| > 0.85 | Auto-store |

**Tips for high-quality entries:**
- Include problem description, root cause, and solution
- Add code snippets or file paths
- Be specific about what was changed and why

---

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
