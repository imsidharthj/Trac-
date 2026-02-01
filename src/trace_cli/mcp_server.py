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
                "Generate a basic HTML trace report from captured evidence. "
                "For a full AI-powered review, use trace.full_review instead."
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
        Tool(
            name="trace.ingest_context",
            description=(
                "Ingest AI conversation context from Antigravity or other sources. "
                "This captures the 'why' behind code changes for better reviews. "
                "Use 'antigravity' source for auto-discovery of current project conversations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Context source: 'antigravity', 'gemini', 'claude'",
                        "default": "antigravity",
                    },
                    "session_uuid": {
                        "type": "string",
                        "description": "Specific session UUID to ingest (for antigravity)",
                    },
                },
            },
        ),
        Tool(
            name="trace.full_review",
            description=(
                "Generate a complete AI-powered code review with HTML report. "
                "Collects git diff, gathers evidence, calls LLM for analysis, "
                "and renders a beautiful HTML report. Returns file path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "staged_only": {
                        "type": "boolean",
                        "description": "Review only staged changes (default: false)",
                        "default": False,
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Open report in browser (default: false)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="trace.get_diff",
            description=(
                "Get the current git diff as structured JSON. "
                "Returns list of changed files with their additions, deletions, and content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "staged_only": {
                        "type": "boolean",
                        "description": "Get only staged changes (default: false)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="trace.analyze_code",
            description=(
                "Analyze code changes with LLM using provided diff and evidence. "
                "Returns AI-generated code review comments and summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_evidence": {
                        "type": "boolean",
                        "description": "Include captured evidence in analysis (default: true)",
                        "default": True,
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Include AI context in analysis (default: true)",
                        "default": True,
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
    elif name == "trace.ingest_context":
        return await _handle_ingest_context(arguments)
    elif name == "trace.full_review":
        return await _handle_full_review_v2(arguments)  # Uses the working v2 implementation
    elif name == "trace.get_diff":
        return await _handle_get_diff(arguments)
    elif name == "trace.analyze_code":
        return await _handle_analyze_code(arguments)
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


async def _handle_ingest_context(arguments: dict) -> list[TextContent]:
    """Ingest AI conversation context."""
    import json
    from .core.adapters.base import get_adapter
    from .core.adapters.antigravity import AntigravityAdapter
    from .core.storage import save_context
    
    source = arguments.get("source", "antigravity")
    session_uuid = arguments.get("session_uuid")
    
    try:
        adapter = get_adapter(source)
        
        if adapter is None:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown adapter: {source}"}),
            )]
        
        # For Antigravity, use auto-discovery or specific UUID
        if source == "antigravity" and isinstance(adapter, AntigravityAdapter):
            if session_uuid:
                # Ingest specific session
                context = adapter.ingest_session(session_uuid)
            else:
                # Auto-discover sessions for current project
                sessions = adapter.discover_sessions()
                if not sessions:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": "No Antigravity sessions found for current project",
                            "hint": "Make sure you're in a project directory that has Antigravity conversation history",
                        }),
                    )]
                
                # Ingest the most recent session
                context = adapter.ingest_session(sessions[0])
        else:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Use 'trace context add --source {source}' from CLI for text input",
                    "hint": "MCP ingest_context currently supports antigravity auto-discovery",
                }),
            )]
        
        # Save the context
        context_path = save_context(context.to_dict())
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "session_id": context.session_id,
                "source": context.source,
                "message_count": len(context.messages),
                "title": context.title,
                "artifacts": context.metadata.get("artifacts", []),
                "context_path": str(context_path),
            }, indent=2),
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


async def _handle_get_diff(arguments: dict) -> list[TextContent]:
    """Get git diff as structured JSON."""
    import json
    
    try:
        from .core.git_context import get_diff, get_staged_diff, GitDiff
        
        staged_only = arguments.get("staged_only", False)
        
        if staged_only:
            diff_result = get_staged_diff()
        else:
            diff_result = get_diff()
        
        if diff_result is None:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "Could not get git diff. Are you in a git repository?"}),
            )]
        
        # Convert to JSON-serializable format
        files = []
        for f in diff_result.files:
            files.append({
                "filename": f.filename,
                "change_type": f.change_type,
                "additions": f.additions,
                "deletions": f.deletions,
                "diff_content": f.diff_content[:3000] if f.diff_content else "",
            })
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "base_ref": diff_result.base_ref,
                "head_ref": diff_result.head_ref,
                "total_additions": diff_result.total_additions,
                "total_deletions": diff_result.total_deletions,
                "file_count": len(files),
                "files": files,
            }, indent=2),
        )]
        
    except Exception as e:
        import traceback
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "traceback": traceback.format_exc()[:500]}),
        )]


async def _handle_analyze_code(arguments: dict) -> list[TextContent]:
    """Analyze code changes with LLM."""
    import json
    import os
    from pathlib import Path
    from datetime import datetime
    
    # Debug log
    debug_log = Path.home() / ".trace_debug.log"
    def log(msg):
        with open(debug_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] ANALYZE: {msg}\n")
    
    log("=== analyze_code started ===")
    
    try:
        from .core.git_context import get_diff, GitDiff
        from .core.storage import list_evidence_sessions, load_evidence, list_context_sessions, load_context
        from .core.config import load_config
        from .core.analyzer import gather_evidence, gather_context, build_review_prompt
        
        include_evidence = arguments.get("include_evidence", True)
        include_context = arguments.get("include_context", True)
        
        # 1. Get diff
        log("Getting git diff...")
        diff = get_diff()
        if diff is None:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "Could not get git diff"}),
            )]
        log(f"Got {len(diff.files)} files")
        
        # 2. Gather evidence if requested
        evidence = ""
        if include_evidence:
            log("Gathering evidence...")
            evidence = gather_evidence()
            log(f"Got {len(evidence)} chars of evidence")
        
        # 3. Gather context if requested
        context = ""
        if include_context:
            log("Gathering context...")
            context = gather_context()
            log(f"Got {len(context)} chars of context")
        
        # 4. Build prompt
        log("Building prompt...")
        messages = build_review_prompt(diff, evidence, context)
        log(f"Prompt built with {len(messages)} messages")
        
        # Calculate sizes for debugging
        diff_chars = len(diff.raw_diff) if hasattr(diff, 'raw_diff') else 0
        total_content = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = total_content // 4  # Rough estimate: 4 chars = 1 token
        
        log(f"=== TOKEN BREAKDOWN ===")
        log(f"Diff size: {diff_chars} chars ({diff_chars // 4} tokens)")
        log(f"Evidence size: {len(evidence)} chars ({len(evidence) // 4} tokens)")
        log(f"Context size: {len(context)} chars ({len(context) // 4} tokens)")
        log(f"Total message content: {total_content} chars")
        log(f"Estimated total tokens: {estimated_tokens}")
        log(f"========================")
        
        # 5. Call LLM
        log("Loading config...")
        config = load_config()
        api_key = config.get_api_key()
        
        if not api_key:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "No API key configured"}),
            )]
        
        log(f"Calling LLM ({config.model})...")
        import litellm
        
        # Set API key
        model = config.model
        if "gpt" in model.lower() or "openai" in model.lower():
            os.environ["OPENAI_API_KEY"] = api_key
        elif "gemini" in model.lower() or "google" in model.lower():
            litellm.api_key = api_key
        elif "claude" in model.lower() or "anthropic" in model.lower():
            os.environ["ANTHROPIC_API_KEY"] = api_key
        
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        log("LLM call completed!")
        
        result_text = response.choices[0].message.content
        log(f"Response length: {len(result_text)}")
        
        # Try to parse as JSON
        try:
            import re
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", result_text)
            if json_match:
                result_json = json.loads(json_match.group(1))
            else:
                result_json = json.loads(result_text)
            
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "model": model,
                    "review": result_json,
                }, indent=2),
            )]
        except json.JSONDecodeError:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "model": model,
                    "raw_response": result_text[:2000],
                }, indent=2),
            )]
        
    except Exception as e:
        import traceback
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()[:500],
            }),
        )]


async def _handle_full_review_v2(arguments: dict) -> list[TextContent]:
    """Generate a complete AI-powered code review with HTML report.
    
    This is a clean reimplementation using the same pattern as analyze_code.
    """
    import json
    import os
    import re
    from pathlib import Path
    from datetime import datetime
    
    # Debug log
    debug_log = Path.home() / ".trace_debug.log"
    def log(msg):
        with open(debug_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] REVIEW_V2: {msg}\n")
    
    log("=== full_review_v2 started ===")
    log(f"Arguments: {arguments}")
    
    try:
        # Step 1: Imports
        log("Step 1: Importing modules...")
        from .core.git_context import get_diff, get_staged_diff, GitDiff
        from .core.storage import list_evidence_sessions, load_evidence
        from .core.config import load_config
        from .core.analyzer import gather_evidence, gather_context, build_review_prompt, ReviewResult
        from .output.renderer import render_review_html, save_trace, open_in_browser
        log("Step 1: Imports OK")
        
        staged_only = arguments.get("staged_only", False)
        open_browser_flag = arguments.get("open_browser", False)
        
        # Step 2: Get diff
        log("Step 2: Getting git diff...")
        if staged_only:
            diff = get_staged_diff()
        else:
            diff = get_diff()
        
        if diff is None:
            log("Step 2: FAILED - No diff")
            return [TextContent(
                type="text",
                text=json.dumps({"error": "Could not get git diff"}),
            )]
        
        diff_files = [
            {
                "filename": f.filename,
                "change_type": f.change_type,
                "additions": f.additions,
                "deletions": f.deletions,
                "diff_content": f.diff_content[:2000] if f.diff_content else "",
            }
            for f in diff.files
        ]
        log(f"Step 2: Git diff OK - {len(diff_files)} files")
        
        # Step 3: Gather evidence
        log("Step 3: Gathering evidence...")
        evidence = gather_evidence()
        log(f"Step 3: Evidence OK - {len(evidence)} chars")
        
        # Step 4: Gather context
        log("Step 4: Gathering context...")
        context = gather_context()
        log(f"Step 4: Context OK - {len(context)} chars")
        
        # Step 5: Build prompt and call LLM
        log("Step 5: Building prompt...")
        messages = build_review_prompt(diff, evidence, context)
        
        # Log token breakdown
        total_content = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = total_content // 4
        log(f"Step 5: Prompt ready - ~{estimated_tokens} tokens")
        
        # Load config and call LLM
        config = load_config()
        model = config.model
        api_key = config.get_api_key()
        
        if not api_key:
            log("Step 5: FAILED - No API key")
            return [TextContent(
                type="text",
                text=json.dumps({"error": "No API key configured"}),
            )]
        
        log(f"Step 5: Calling LLM ({model})...")
        import litellm
        
        # Set API key
        if "gpt" in model.lower() or "openai" in model.lower():
            os.environ["OPENAI_API_KEY"] = api_key
        elif "gemini" in model.lower() or "google" in model.lower():
            litellm.api_key = api_key
        elif "claude" in model.lower() or "anthropic" in model.lower():
            os.environ["ANTHROPIC_API_KEY"] = api_key
        
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        log("Step 5: LLM call completed!")
        
        result_text = response.choices[0].message.content
        log(f"Step 5: Response length: {len(result_text)}")
        
        # Step 6: Parse LLM response
        log("Step 6: Parsing response...")
        try:
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", result_text)
            if json_match:
                review_data = json.loads(json_match.group(1))
            else:
                review_data = json.loads(result_text)
            
            review_result = ReviewResult.from_dict(review_data)
            review_result.model_used = model
            log("Step 6: Parsed as JSON OK")
        except json.JSONDecodeError:
            log("Step 6: JSON parse failed, using raw response")
            review_result = ReviewResult(
                summary=result_text[:500],
                status="parsed_error",
                evidence_analysis="Could not parse structured response",
                model_used=model,
            )
        
        # Step 7: Gather evidence sessions for HTML
        log("Step 7: Gathering evidence for HTML...")
        evidence_sessions = list_evidence_sessions()[:10]
        evidence_data = []
        for session in evidence_sessions:
            data = load_evidence(session.get("session_id", ""))
            if data:
                evidence_data.append(data)
        log(f"Step 7: Got {len(evidence_data)} evidence sessions")
        
        # Step 8: Render HTML
        log("Step 8: Rendering HTML...")
        html_content = render_review_html(
            review_result=review_result.to_dict() if hasattr(review_result, 'to_dict') else review_result,
            evidence_sessions=evidence_data,
            diff_files=diff_files,
            model=model,
        )
        log(f"Step 8: HTML rendered - {len(html_content)} chars")
        
        # Step 9: Save trace
        log("Step 9: Saving trace...")
        file_path = save_trace(html_content)
        log(f"Step 9: Saved to {file_path}")
        
        # Step 10: Optionally open browser
        if open_browser_flag:
            log("Step 10: Opening browser...")
            open_in_browser(file_path)
        
        log("=== full_review_v2 SUCCESS ===")
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "file_path": str(file_path),
                "status": getattr(review_result, 'status', 'complete'),
                "summary": getattr(review_result, 'summary', 'Review generated')[:200],
                "evidence_count": len(evidence_data),
                "diff_files_count": len(diff_files),
                "model": model,
            }, indent=2),
        )]
        
    except Exception as e:
        import traceback
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        log(f"TRACEBACK: {traceback.format_exc()}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()[:500],
            }),
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
