"""FastMCP server for PendoMind - simple memory persistence for Claude.

This module provides a minimal, intuitive API for storing and retrieving
memories. Uses SQLite + sqlite-vec for zero-setup vector search.

Usage:
    python -m pendomind.main

Configuration:
    Add to Claude Code's MCP settings:
    {
        "mcpServers": {
            "pendomind": {
                "command": "python",
                "args": ["-m", "pendomind.main"]
            }
        }
    }
"""

from typing import Annotated

from fastmcp import FastMCP

from pendomind.memory import MemoryStore

# Initialize FastMCP server
mcp = FastMCP(
    name="pendomind",
    instructions="""PendoMind is a personal memory layer for Claude.

Use simple verbs to interact:
- remember() to store something
- search() to find memories semantically
- list_memories() to see all memories
- forget() to delete a memory

Memory types: fact (verified info), note (default, general), learning (insights)""",
)

# Initialize memory store (uses ~/.pendomind/memory.db by default)
memory = MemoryStore()


@mcp.tool()
async def remember(
    content: Annotated[str, "What to remember"],
    tags: Annotated[list[str] | None, "Optional tags for categorization"] = None,
    type: Annotated[str, "Type: fact, note, learning (default: note)"] = "note",
) -> dict:
    """Store a memory. Automatically handles duplicates.

    If very similar content already exists, updates it instead of creating
    a duplicate. Use tags to help organize and find memories later.

    Examples:
        - remember("Python's GIL only affects CPU-bound threads", tags=["python", "concurrency"])
        - remember("The auth service uses JWT tokens with 1h expiry", type="fact")
    """
    return await memory.store(content=content, type=type, tags=tags)


@mcp.tool()
async def search(
    query: Annotated[str, "What to search for"],
    limit: Annotated[int, "Max results (default: 10)"] = 10,
    type: Annotated[str | None, "Filter by type: fact, note, learning"] = None,
) -> list[dict]:
    """Search memories semantically.

    Finds memories similar in meaning to your query, not just exact matches.
    Results are ranked by relevance.

    Examples:
        - search("python threading") -> finds memories about GIL, concurrency, etc.
        - search("authentication", type="fact") -> finds verified auth-related facts
    """
    return await memory.search(query=query, limit=limit, type_filter=type)


@mcp.tool()
async def forget(
    id: Annotated[str, "Memory ID to delete"],
) -> dict:
    """Delete a memory by ID.

    Use list_memories() or search() to find the ID of the memory you want to delete.
    This action is permanent.
    """
    return await memory.delete(memory_id=id)


@mcp.tool()
async def list_memories(
    limit: Annotated[int, "Max results (default: 50)"] = 50,
    type: Annotated[str | None, "Filter by type: fact, note, learning"] = None,
) -> list[dict]:
    """List all memories.

    Returns memories ordered by creation date (newest first).
    Use type filter to see only specific categories.

    Examples:
        - list_memories() -> all memories
        - list_memories(type="fact") -> only verified facts
        - list_memories(limit=10) -> most recent 10 memories
    """
    return await memory.list_all(limit=limit, type_filter=type)


@mcp.tool()
async def recall(
    query: Annotated[str, "Context query"],
    limit: Annotated[int, "Max entries (default: 5)"] = 5,
) -> dict:
    """Get relevant context for a prompt.

    Similar to search() but returns structured context suitable for
    including in prompts. Use when you need background information.

    Example:
        - recall("user authentication") -> returns context about auth
    """
    entries = await memory.search(query=query, limit=limit)
    return {
        "context": entries,
        "query": query,
        "count": len(entries),
    }


@mcp.tool()
async def similar(
    content: Annotated[str, "Content to check for duplicates"],
) -> list[dict]:
    """Find similar existing memories.

    Use this to check if something is already stored before adding it.
    Returns memories with similarity scores (higher = more similar).

    Example:
        - similar("Python uses the GIL for thread safety")
          -> shows if you already have a memory about Python's GIL
    """
    return await memory.find_similar(content=content)


def main():
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
