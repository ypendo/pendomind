# PendoMind - The Ultimate Engineering Knowledge Base

## Hackathon 26.2 POC

**Project**: PendoMind
**Owner**: @Yuri Bondarenko
**Duration**: 1-3 days

---

## Problem

Pendo engineers constantly solve problems that others have solved before - debugging errors, fixing bugs, building features, responding to incidents. This knowledge is scattered across Confluence, GitHub, Slack, and people's heads. When someone leaves, tribal knowledge is lost.

## Solution

Build a persistent vector DB with MCP integration that **automatically learns from ALL engineering work** with Claude Code - bug fixes, debugging sessions, feature development, incident response, and more. An ever-growing knowledge base that makes every Pendo engineer smarter.

**Key Innovation**: Built-in **data quality control** ensures only valuable knowledge is stored - no garbage data polluting the knowledge base.

---

## Use Cases

| Scenario        | How PendoMind Helps                                                |
| --------------- | ------------------------------------------------------------------ |
| **Bug Fix**     | "Have we seen this error before?" → Find similar bugs and fixes    |
| **Debugging**   | "Why is this service slow?" → Find past debugging sessions         |
| **New Feature** | "How did we implement X?" → Find similar implementations           |
| **On-Call**     | "Service Y is alerting" → Find past incidents and resolutions      |
| **Onboarding**  | "How does aggregation work?" → Find architectural decisions        |
| **Code Review** | "Is this pattern used elsewhere?" → Find similar code patterns     |

---

## Architecture

```text
Claude Code ──stdio──▶ FastMCP Server ──▶ Qdrant (Docker)
                       │                   localhost:6333
                       │
                       ├── QualityMiddleware (intercepts remember())
                       ├── QualityScorer (scores content quality)
                       ├── PendingStore (user confirmation workflow)
                       └── KnowledgeBase (Qdrant wrapper)
```

### Tech Stack

| Component  | Technology                    |
| ---------- | ----------------------------- |
| Vector DB  | Qdrant (Docker)               |
| Framework  | **FastMCP** (Python)          |
| MCP Server | FastMCP stdio transport       |
| Embeddings | **FastEmbed** (local, free)   |

> **Why FastEmbed over OpenAI?**
> - 🆓 **100% free** - no API keys, no costs
> - 🔒 **Private** - all data stays on your machine
> - ⚡ **Fast** - runs locally using ONNX Runtime
> - 📦 **Lightweight** - model cached after first download (~130MB)


### MCP Tools

| Tool                               | Description                              |
| ---------------------------------- | ---------------------------------------- |
| `search_knowledge(query, type_filter?, limit?)`             | Semantic search across all knowledge     |
| `remember_knowledge(content, type, tags, source?, file_paths?)`    | Analyze + store with quality workflow    |
| `confirm_knowledge(pending_id, approved)`     | Confirm/reject pending storage           |
| `recall_context(query, type_filter?, limit?)`             | Retrieve formatted context                |
| `find_similar(content)`            | Find duplicates before storing           |
| `get_file_context(file_path)`           | Get knowledge related to file/service    |
| `list_pending()`                   | List all pending entries awaiting confirmation |

### Knowledge Types

Single Qdrant collection with type filtering (more efficient than multiple collections):
- `bug` - Bug reports, root causes, and fixes
- `feature` - Feature implementations, design decisions
- `incident` - Incident reports, RCAs, resolutions
- `debugging` - Debugging sessions, symptoms, solutions
- `architecture` - System design, service dependencies
- `error` - Error patterns and their fixes
- `investigation` - Exploratory discoveries about architecture, code, or behavior

---

## Data Quality Control

### The Problem

Without quality control, the knowledge base would fill with:
- Incomplete or vague entries ("fixed the bug")
- Duplicate content
- Low-relevance chat snippets
- Sensitive data (passwords, API keys)

### Solution: Three-Tier Quality System

| Score Range | Action | User Involvement |
|-------------|--------|------------------|
| **< 0.65** | Auto-reject | Informed with reason |
| **0.65 - 0.85** | Pending review | Must call `remember_confirm()` |
| **> 0.85** | Auto-approve | Stored automatically |

### Quality Scoring Algorithm

```
Composite Score = (0.40 × Relevance) + (0.35 × Completeness) + (0.25 × Credibility)
```

#### Relevance (40% weight)
- Domain keyword density (bug, fix, error, implementation, etc.)
- Technical content detection (code blocks, stack traces)
- Type-specific patterns (RCA for incidents, diagrams for architecture)

#### Completeness (35% weight)
- Content length (penalizes very short entries)
- Structure markers (problem, cause, solution, context)
- Actionable information (steps, code examples)

#### Credibility (25% weight)
Source reliability scores:
| Source | Score | Rationale |
|--------|-------|-----------|
| GitHub | 0.95 | Code-reviewed, contextual |
| Confluence | 0.85 | Documented, reviewed |
| Jira | 0.80 | Structured tickets |
| Claude Session | 0.70 | AI-assisted, needs verification |
| Slack | 0.60 | Conversational, may lack context |

### Deduplication

Before storing new knowledge:
1. Search for similar content (cosine similarity > 0.90)
2. Show duplicates with options: skip, merge, or keep both
3. Use content hash + source for exact dedup via deterministic IDs

### Configuration

Quality rules are configurable via `config/quality_rules.yaml`:

```yaml
thresholds:
  min_quality_score: 0.65      # Below: auto-reject
  auto_approve_score: 0.85     # Above: auto-approve
  duplicate_similarity: 0.90   # Dedup threshold

filtering:
  excluded_patterns:           # Security: never store
    - "password"
    - "api_key"
    - "secret"
    - "token"
  min_content_length: 15       # Words
  max_content_length: 5000     # Words

types:
  allowed:
    - bug
    - feature
    - incident
    - debugging
    - architecture
    - error
    - investigation
```

### User Confirmation Workflow

```
User: "remember this bug fix..."
         │
         ▼
┌─────────────────────────────────────┐
│ 1. Middleware intercepts remember() │
│    - Check type validity            │
│    - Check excluded patterns        │
│    - Check content length           │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ 2. Quality Scorer calculates score  │
│    - Relevance: keywords, code      │
│    - Completeness: structure        │
│    - Credibility: source weight     │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ 3. Deduplication check              │
│    - Find similar existing entries  │
│    - Return duplicate warnings      │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 4. Decision                                          │
│    score < 0.65  → REJECT (return reason)           │
│    score > 0.85  → AUTO-STORE (return success)      │
│    otherwise     → PENDING (return pending_id)      │
└─────────────────────────────────────────────────────┘
         │
         ▼ (if PENDING)
┌─────────────────────────────────────┐
│ 5. User reviews quality analysis    │
│    - Score breakdown                │
│    - Duplicate warnings             │
│    - Recommendations                │
│                                     │
│ User calls: remember_confirm(id)    │
└─────────────────────────────────────┘
```

---

## Project Structure

```text
pendomind/
├── pyproject.toml
├── README.md
├── docs/
│   ├── PENDOMIND_PLAN.md       # This file
│   └── tdd.md                  # Development guide
├── config/
│   └── quality_rules.yaml      # Quality thresholds
├── src/pendomind/
│   ├── __init__.py
│   ├── main.py                 # FastMCP server entry
│   ├── knowledge.py            # Qdrant wrapper
│   ├── tools.py                # MCP tools + PendingStore
│   ├── quality.py              # Quality scoring
│   ├── config.py               # Config loader
│   └── middleware.py           # Quality control middleware
└── tests/
    ├── conftest.py
    ├── test_quality.py
    ├── test_knowledge.py
    ├── test_tools.py
    ├── test_middleware.py
    └── test_integration.py
```

---

## Quick Start

```bash
# 1. Start Qdrant
docker run -d -p 6333:6333 --name pendomind-qdrant qdrant/qdrant

# 2. Install PendoMind
pip install -e .

# 3. Run MCP server (no API keys needed!)
python -m pendomind.main
```

> **Note**: The first time you run PendoMind, FastEmbed will download the embedding model (~130MB).
> After that, everything runs locally - no internet required!

## Claude Code Config

Add to `~/.claude.json` (mcpServers section):

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

## Implementation Plan

### Day 1: Foundation + Quality Scoring

- [x] Set up Python project with FastMCP
- [ ] Start Qdrant Docker container
- [ ] Create config module with quality_rules.yaml
- [ ] Implement quality scoring (relevance, completeness, credibility)
- [ ] Implement pending store for user confirmation

### Day 2: Core Features + Middleware

- [ ] Implement knowledge.py (Qdrant wrapper)
- [ ] Implement quality control middleware
- [ ] Implement MCP tools (search, remember, remember_confirm, etc.)
- [ ] Connect to Claude Code

### Day 3: Polish & Demo

- [ ] Demo scenario 1: Bug fix with similar past bugs
- [ ] Demo scenario 2: Feature dev with architecture context
- [ ] Demo scenario 3: Debugging with error pattern matching
- [ ] Record 3-minute video
- [ ] Document setup instructions

---

## Success Criteria

1. Claude Code can search past work semantically (bugs, features, incidents)
2. **Quality control prevents low-quality entries** from polluting the knowledge base
3. **User confirmation workflow** for medium-quality content
4. Knowledge persists across sessions and grows organically
5. Demo shows 3 scenarios: bug fix, feature dev, debugging

---

## References

- [FastMCP Docs](https://gofastmcp.com)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [FastEmbed GitHub](https://github.com/qdrant/fastembed) - Local embeddings, no API needed
- [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) - Embedding model used
