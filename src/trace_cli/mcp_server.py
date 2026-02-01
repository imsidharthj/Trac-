"""Tracé MCP Server — Model Context Protocol interface for AI agents.

This module exposes Tracé's capabilities to AI agents (Codex, Claude Desktop, etc.)
via the Model Context Protocol (MCP) over STDIO transport.

The server provides three tools:
1. trace.run_and_capture — Execute commands and capture evidence
2. trace.get_recent_evidence — List recent evidence sessions
3. trace.generate_report — Generate HTML trace report

SAFETY: All output goes to stderr to preserve STDIO JSON-RPC transport.
"""

import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create MCP server instance
server = Server("trace")


# ============================================================================
# Tool Definitions
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the list of available tools."""
    return [
        Tool(
            name="trace.run_and_capture",
            description=(
                "Execute a shell command, stream the output to the console (visible to user), "
                "and capture it as immutable evidence for later review. "
                "⚠️ CAUTION: This executes code on the user's machine. "
                "Only use this if the user has explicitly requested command execution."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g., 'pytest -v', 'npm test')",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory for command execution",
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="trace.get_recent_evidence",
            description=(
                "Retrieve a list of recently captured command outputs/evidence. "
                "Returns session IDs, commands, exit codes, and timestamps."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of sessions to return (default: 10)",
                        "default": 10,
                    },
                },
            },
        ),
        Tool(
            name="trace.generate_report",
            description=(
                "Generate a shareable HTML trace report based on recent evidence and code changes. "
                "Returns the file path to the generated report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "open_browser": {
                        "type": "boolean",
                        "description": "Open the report in the default browser (default: false)",
                        "default": False,
                    },
                },
            },
        ),
    ]


# ============================================================================
# Tool Implementations
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    
    if name == "trace.run_and_capture":
        return await _handle_run_and_capture(arguments)
    elif name == "trace.get_recent_evidence":
        return await _handle_get_recent_evidence(arguments)
    elif name == "trace.generate_report":
        return await _handle_generate_report(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _handle_run_and_capture(arguments: dict) -> list[TextContent]:
    """Execute a command and capture evidence."""
    import json
    from .core.capture import run_and_capture
    
    command = arguments.get("command", "")
    cwd = arguments.get("cwd")
    
    if not command:
        return [TextContent(
            type="text",
            text=json.dumps({"error": "command is required"}),
        )]
    
    try:
        # Run with quiet=True to preserve STDIO transport
        result = run_and_capture(
            command=command,
            cwd=cwd,
            quiet=True,
        )
        
        # Return structured result
        response = {
            "session_id": result.session_id,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "stdout_tail": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stderr_tail": result.stderr[-500:] if len(result.stderr) > 500 else result.stderr,
            "evidence_path": str(result.evidence_path),
        }
        
        return [TextContent(type="text", text=json.dumps(response, indent=2))]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


async def _handle_get_recent_evidence(arguments: dict) -> list[TextContent]:
    """List recent evidence sessions."""
    import json
    from .core.storage import list_evidence_sessions
    
    limit = arguments.get("limit", 10)
    
    try:
        sessions = list_evidence_sessions()[:limit]
        
        # Format for agent consumption
        result = []
        for session in sessions:
            result.append({
                "session_id": session.get("session_id", ""),
                "command": session.get("command", ""),
                "exit_code": session.get("exit_code", None),
                "timestamp": session.get("timestamp", ""),
                "duration_ms": session.get("duration_ms", 0),
            })
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


async def _handle_generate_report(arguments: dict) -> list[TextContent]:
    """Generate an HTML trace report."""
    import json
    from .core.storage import list_evidence_sessions, load_evidence
    from .output.renderer import render_review_html, save_trace, open_in_browser
    
    open_browser_flag = arguments.get("open_browser", False)
    
    try:
        # Gather recent evidence
        sessions = list_evidence_sessions()[:5]
        evidence_data = []
        for session in sessions:
            data = load_evidence(session.get("session_id", ""))
            if data:
                evidence_data.append(data)
        
        if not evidence_data:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "No evidence found. Run some commands first."}),
            )]
        
        # Create a basic review result (without LLM analysis)
        review_result = {
            "summary": f"Evidence report with {len(evidence_data)} captured sessions.",
            "status": "evidence_only",
            "evidence_analysis": "This report contains captured evidence without AI analysis.",
            "files": [],
        }
        
        # Render HTML
        html_content = render_review_html(
            review_result=review_result,
            evidence_sessions=evidence_data,
            diff_files=[],
            model="N/A (evidence only)",
        )
        
        # Save the trace
        file_path = save_trace(html_content)
        
        # Optionally open in browser
        if open_browser_flag:
            open_in_browser(file_path)
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "file_path": str(file_path),
                "evidence_count": len(evidence_data),
            }, indent=2),
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


# ============================================================================
# Server Entry Point
# ============================================================================

async def run_server():
    """Run the MCP server on STDIO."""
    # Log to stderr to avoid corrupting STDIO transport
    print("Tracé MCP Server starting...", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """Entry point for the MCP server."""
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
