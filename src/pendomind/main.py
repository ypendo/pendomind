"""FastMCP server for PendoMind engineering knowledge base.

This module creates and configures the MCP server that exposes
knowledge base tools to Claude Code and other MCP clients.

Uses FastEmbed for local embeddings - no API keys required!

Usage:
    python -m pendomind.main

Configuration:
    Add to Claude Code's MCP settings:
    {
        "mcpServers": {
            "pendomind": {
                "command": "python",
                "args": ["-m", "pendomind.main"],
                "cwd": "/path/to/pendomind"
            }
        }
    }
"""

from typing import Annotated

from fastmcp import FastMCP

from pendomind.config import PendoMindConfig
from pendomind.knowledge import KnowledgeBase
from pendomind.middleware import QualityMiddleware
from pendomind.tools import (
    PendingStore,
    get_context,
    list_similar,
    recall,
    remember,
    remember_confirm,
    search,
)

# Initialize FastMCP server
mcp = FastMCP(
    name="pendomind",
    instructions="""PendoMind is an engineering knowledge base for storing and retrieving
technical knowledge. Use search() to find relevant information, remember() to store new
knowledge (with quality control), and get_context() for file-related context.""",
)

# Initialize shared dependencies
config = PendoMindConfig()
kb = KnowledgeBase(config)
middleware = QualityMiddleware(config)
pending_store = PendingStore(config=config)

# Wire up middleware dependencies
middleware.kb = kb
middleware.pending_store = pending_store


@mcp.tool()
async def search_knowledge(
    query: Annotated[str, "Natural language search query"],
    type_filter: Annotated[
        str | None, "Filter by type: bug, feature, incident, debugging, architecture, error, investigation"
    ] = None,
    limit: Annotated[int, "Maximum results to return (default 10)"] = 10,
) -> list[dict]:
    """Search the engineering knowledge base for relevant entries.

    Returns matching entries with relevance scores. Use type_filter
    to narrow results to a specific knowledge type.
    """
    return await search(query, type_filter=type_filter, limit=limit, kb=kb)


@mcp.tool()
async def remember_knowledge(
    content: Annotated[str, "The knowledge to store (detailed description)"],
    type: Annotated[
        str,
        "Type: bug, feature, incident, debugging, architecture, error, investigation",
    ],
    tags: Annotated[list[str], "Tags for categorization"],
    source: Annotated[
        str, "Source: github, confluence, jira, slack, claude_session"
    ] = "claude_session",
    file_paths: Annotated[
        list[str] | None, "Related file paths (optional)"
    ] = None,
) -> dict:
    """Store engineering knowledge with quality control.

    Content goes through quality scoring:
    - High quality (>0.85): Auto-stored
    - Medium quality (0.65-0.85): Pending - call confirm_knowledge() to approve
    - Low quality (<0.65): Rejected with recommendations

    Include problem description, root cause, and solution for best scores.
    """
    return await remember(
        content=content,
        type=type,
        tags=tags,
        source=source,
        file_paths=file_paths,
        middleware=middleware,
    )


@mcp.tool()
async def confirm_knowledge(
    pending_id: Annotated[str, "ID of the pending item to confirm"],
    approved: Annotated[bool, "True to approve and store, False to reject"],
) -> dict:
    """Confirm or reject a pending knowledge entry.

    Use this after remember_knowledge() returns status='pending'.
    Pending items expire after 30 minutes.
    """
    return await remember_confirm(
        pending_id=pending_id,
        approved=approved,
        pending_store=pending_store,
        kb=kb,
    )


@mcp.tool()
async def recall_context(
    query: Annotated[str, "Natural language query for context"],
    type_filter: Annotated[str | None, "Optional type filter"] = None,
    limit: Annotated[int, "Maximum entries (default 5)"] = 5,
) -> dict:
    """Retrieve relevant context from the knowledge base.

    Similar to search but formatted for inclusion in prompts.
    Returns context entries relevant to the query.
    """
    return await recall(query, type_filter=type_filter, limit=limit, kb=kb)


@mcp.tool()
async def find_similar(
    content: Annotated[str, "Content to check for duplicates"],
) -> list[dict]:
    """Find similar entries before storing new knowledge.

    Use this to check if content already exists before calling
    remember_knowledge(). Returns entries with similarity scores.
    """
    return await list_similar(content, kb=kb)


@mcp.tool()
async def get_file_context(
    file_path: Annotated[str, "Path to the file"],
) -> dict:
    """Get knowledge related to a specific file.

    Returns all knowledge entries that reference this file path.
    Useful when working on a file to see historical context.
    """
    return await get_context(file_path, kb=kb)


@mcp.tool()
async def list_pending() -> list[dict]:
    """List all pending knowledge entries awaiting confirmation.

    Returns pending items that haven't been confirmed or expired.
    """
    items = pending_store.list_pending()
    return [
        {
            "id": item.id,
            "type": item.type,
            "content_preview": item.content[:100] + "..." if len(item.content) > 100 else item.content,
            "quality_score": getattr(item.quality_analysis, "composite_score", None),
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


def main():
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
