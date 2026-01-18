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
    delete,
    get_context,
    list_all,
    list_similar,
    recall,
    remember,
    remember_confirm,
    search,
    update,
    upsert,
)

# Initialize FastMCP server
mcp = FastMCP(
    name="pendomind",
    instructions="""PendoMind is an engineering knowledge base for storing and retrieving
technical knowledge. Use search_knowledge() to find relevant information.

IMPORTANT - Choosing the right tool for storing knowledge:
- upsert_knowledge(): Use when UPDATING existing knowledge (incidents, bugs, features).
  It automatically finds similar entries and updates them instead of creating duplicates.
  This is the RECOMMENDED tool for ongoing investigations or evolving documentation.
- remember_knowledge(): Use for storing BRAND NEW knowledge that doesn't update existing entries.
  Has quality control with auto-approve/pending/reject workflow.
- update_knowledge(id): Use when you have a specific entry ID to update directly.
- delete_knowledge(id): Use to remove obsolete entries.""",
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
async def list_all_knowledge(
    limit: Annotated[int, "Maximum entries to return (default 100)"] = 100,
    type_filter: Annotated[
        str | None, "Filter by type: bug, feature, incident, debugging, architecture, error, investigation"
    ] = None,
) -> list[dict]:
    """List all stored knowledge entries with short summaries.

    Returns entries with ID, type, 150-char summary, tags, source, file paths, and timestamps.
    Useful for browsing the entire knowledge base without semantic search.
    """
    return await list_all(limit=limit, type_filter=type_filter, kb=kb)


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


@mcp.tool()
async def upsert_knowledge(
    content: Annotated[str, "The knowledge to store or update"],
    type: Annotated[
        str,
        "Type: bug, feature, incident, debugging, architecture, error, investigation",
    ],
    tags: Annotated[list[str], "Tags for categorization"],
    source: Annotated[
        str, "Source: github, confluence, jira, slack, claude_session"
    ] = "claude_session",
    file_paths: Annotated[list[str] | None, "Related file paths (optional)"] = None,
    similarity_threshold: Annotated[
        float, "How similar an existing entry must be to update (default 0.85)"
    ] = 0.85,
) -> dict:
    """Smart update-or-create: finds similar entry and updates it, or creates new.

    RECOMMENDED for updating existing knowledge (incidents, bugs, ongoing investigations).
    Automatically finds the most similar existing entry and updates it instead of
    creating duplicates. If no similar entry is found, creates a new one.

    Example workflow:
    - Day 1: upsert_knowledge("Investigating 502 errors...", type="incident")  # creates new
    - Day 2: upsert_knowledge("Found: upstream timeout...", type="incident")   # updates existing
    - Day 3: upsert_knowledge("RESOLVED: Fixed by...", type="incident")        # updates same entry
    """
    return await upsert(
        content=content,
        type=type,
        tags=tags,
        source=source,
        file_paths=file_paths,
        similarity_threshold=similarity_threshold,
        kb=kb,
    )


@mcp.tool()
async def update_knowledge(
    id: Annotated[str, "ID of the entry to update (use search_knowledge to find IDs)"],
    content: Annotated[str | None, "New content (re-embeds if changed)"] = None,
    tags: Annotated[list[str] | None, "New tags list"] = None,
    type: Annotated[str | None, "New type"] = None,
    file_paths: Annotated[list[str] | None, "New file paths list"] = None,
) -> dict:
    """Update an existing knowledge entry by ID.

    Use search_knowledge() or list_all_knowledge() to find the entry ID first.
    Only provided fields are updated; others remain unchanged.
    If content changes, the entry is re-embedded for accurate search.
    """
    return await update(id=id, content=content, tags=tags, type=type, file_paths=file_paths, kb=kb)


@mcp.tool()
async def delete_knowledge(
    id: Annotated[str, "ID of the entry to delete"],
) -> dict:
    """Delete a knowledge entry by ID.

    Use this to remove obsolete or incorrect entries.
    This action is irreversible.
    """
    return await delete(id=id, kb=kb)


def main():
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
