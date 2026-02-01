"""Tracé CLI — The Agentic AI PR Reviewer & Evidence Collector.

Main CLI application using Typer.

Commands:
    trace run <command>     Execute and record a command
    trace capture --log     Import an existing log file
    trace list              List captured evidence sessions
    trace context add       Add context from an AI session
    trace context list      List stored context sessions
    trace context show      Display a context session
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .core.capture import capture_log_file, run_and_capture
from .core.storage import (
    list_context_sessions,
    list_evidence_sessions,
    load_context,
    save_context,
)
from .core.adapters import GeminiAdapter
from .core.adapters.base import get_adapter, list_adapters

# Initialize Typer app
app = typer.Typer(
    name="trace",
    help="Tracé — The Agentic AI PR Reviewer & Evidence Collector",
    add_completion=True,
    rich_markup_mode="rich",
)

# Context subcommand group
context_app = typer.Typer(
    name="context",
    help="Manage ingested AI session context",
)
app.add_typer(context_app, name="context")

console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold]Tracé[/bold] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Tracé — Capture evidence, ingest context, generate reviews."""
    pass


@app.command()
def run(
    command: Annotated[
        list[str],
        typer.Argument(
            help="The command to execute and record.",
        ),
    ],
) -> None:
    """Execute a command and capture its output as evidence.
    
    The command output is streamed to the console in real-time while
    being recorded. Evidence is saved to .ai/evidence/ for later use
    in code reviews.
    
    Examples:
        trace run pytest -v
        trace run npm test
        trace run make build
    """
    if not command:
        console.print("[red]Error:[/red] No command provided.")
        raise typer.Exit(1)
    
    # Join command parts into a single string
    command_str = " ".join(command)
    
    # Execute and capture
    result = run_and_capture(command_str)
    
    # Exit with the same code as the captured command
    raise typer.Exit(result.exit_code)


@app.command()
def capture(
    log: Annotated[
        Path,
        typer.Option(
            "--log",
            "-l",
            help="Path to a log file to import as evidence.",
            exists=True,
            readable=True,
        ),
    ],
) -> None:
    """Import an existing log file as evidence.
    
    Use this to capture output from CI/CD pipelines, build servers,
    or other external tools.
    
    Examples:
        trace capture --log ./build.log
        trace capture -l /tmp/pytest-output.txt
    """
    try:
        capture_log_file(log)
    except FileNotFoundError:
        raise typer.Exit(1)


@app.command(name="list")
def list_sessions() -> None:
    """List all captured evidence sessions.
    
    Shows a table of all evidence sessions stored in .ai/evidence/,
    including commands, exit codes, and timestamps.
    """
    sessions = list_evidence_sessions()
    
    if not sessions:
        console.print("[dim]No evidence sessions found.[/dim]")
        console.print("[dim]Run 'trace run <command>' to capture your first session.[/dim]")
        return
    
    # Build a table
    table = Table(
        title="📋 Evidence Sessions",
        show_header=True,
        header_style="bold cyan",
    )
    
    table.add_column("Session ID", style="dim")
    table.add_column("Command / Source")
    table.add_column("Exit", justify="center")
    table.add_column("Timestamp")
    
    for session in sessions:
        exit_code = session.get("exit_code")
        if exit_code is None:
            exit_style = "dim"
            exit_display = "—"
        elif exit_code == 0:
            exit_style = "green"
            exit_display = "✓ 0"
        else:
            exit_style = "red"
            exit_display = f"✗ {exit_code}"
        
        # Truncate long commands
        cmd = session.get("command", "N/A")
        if len(cmd) > 50:
            cmd = cmd[:47] + "..."
        
        table.add_row(
            session.get("session_id", "?"),
            cmd,
            f"[{exit_style}]{exit_display}[/{exit_style}]",
            session.get("timestamp", "")[:19] if session.get("timestamp") else "—",
        )
    
    console.print(table)


# ============================================================================
# Context Commands
# ============================================================================

@context_app.command(name="add")
def context_add(
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Source adapter (e.g., 'gemini', 'claude').",
        ),
    ] = "gemini",
    file: Annotated[
        Optional[Path],
        typer.Option(
            "--file",
            "-f",
            help="Path to a file to import (optional).",
            exists=True,
            readable=True,
        ),
    ] = None,
) -> None:
    """Add context from an AI session.
    
    Ingests conversation history from external AI tools (Gemini, Claude, etc.)
    as context for code reviews. Content is scanned and sensitive data
    (API keys, tokens) is automatically redacted.
    
    This is an OPT-IN feature. No external data is read automatically.
    
    Examples:
        trace context add --source gemini              # Paste from clipboard
        trace context add --source gemini --file chat.json
    """
    # Get the adapter
    adapter = get_adapter(source)
    if not adapter:
        available = ", ".join(list_adapters()) or "none"
        console.print(f"[red]Error:[/red] Unknown source '{source}'")
        console.print(f"[dim]Available adapters: {available}[/dim]")
        raise typer.Exit(1)
    
    console.print(f"[bold]Adding context from: {adapter.get_name()}[/bold]")
    console.print(f"[dim]{adapter.get_description()}[/dim]")
    console.print()
    
    try:
        if file:
            # Import from file
            console.print(f"[blue]Importing from:[/blue] {file}")
            context_session = adapter.ingest_file(str(file))
        else:
            # Prompt for text input
            console.print("[yellow]Paste your conversation below.[/yellow]")
            console.print("[dim]Press Ctrl+D (Unix) or Ctrl+Z (Windows) when done.[/dim]")
            console.print()
            
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            
            text = "\n".join(lines)
            
            if not text.strip():
                console.print("[red]Error:[/red] No content provided.")
                raise typer.Exit(1)
            
            context_session = adapter.ingest_text(text)
        
        # Save the context
        context_path = save_context(context_session.to_dict())
        
        # Show summary
        console.print()
        console.print(Panel(
            f"[green]✓ Context saved[/green]\n\n"
            f"Session ID: [bold]{context_session.session_id}[/bold]\n"
            f"Source: {context_session.source}\n"
            f"Messages: {len(context_session.messages)}\n"
            f"Title: {context_session.title or '(untitled)'}",
            title="Context Ingested",
            border_style="green",
        ))
        console.print(f"[dim]Saved to: {context_path}[/dim]")
        
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to ingest context: {e}")
        raise typer.Exit(1)


@context_app.command(name="list")
def context_list() -> None:
    """List all stored context sessions.
    
    Shows a table of all context sessions stored in .ai/context/,
    including source, message count, and timestamps.
    """
    sessions = list_context_sessions()
    
    if not sessions:
        console.print("[dim]No context sessions found.[/dim]")
        console.print("[dim]Run 'trace context add --source gemini' to add your first context.[/dim]")
        return
    
    # Build a table
    table = Table(
        title="🧠 Context Sessions",
        show_header=True,
        header_style="bold magenta",
    )
    
    table.add_column("Session ID", style="dim")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("Messages", justify="center")
    table.add_column("Created")
    
    for session in sessions:
        title = session.get("title", "(untitled)")
        if title and len(title) > 40:
            title = title[:37] + "..."
        
        table.add_row(
            session.get("session_id", "?"),
            session.get("source", "?"),
            title or "—",
            str(session.get("message_count", 0)),
            session.get("created_at", "")[:19] if session.get("created_at") else "—",
        )
    
    console.print(table)


@context_app.command(name="show")
def context_show(
    session_id: Annotated[
        str,
        typer.Argument(help="The session ID to display."),
    ],
) -> None:
    """Display a context session.
    
    Shows the full content of a stored context session,
    including all messages in the conversation.
    
    Examples:
        trace context show abc12345
    """
    context_data = load_context(session_id)
    
    if not context_data:
        console.print(f"[red]Error:[/red] Context session '{session_id}' not found.")
        raise typer.Exit(1)
    
    # Show header
    console.print(Panel(
        f"Session ID: [bold]{context_data.get('session_id')}[/bold]\n"
        f"Source: {context_data.get('source')}\n"
        f"Title: {context_data.get('title', '(untitled)')}\n"
        f"Created: {context_data.get('created_at', 'N/A')}",
        title="🧠 Context Session",
        border_style="magenta",
    ))
    
    # Show messages
    messages = context_data.get("messages", [])
    if not messages:
        console.print("[dim]No messages in this session.[/dim]")
        return
    
    console.print()
    console.print(f"[bold]Messages ({len(messages)}):[/bold]")
    console.print()
    
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        if role == "user":
            role_style = "bold blue"
            role_icon = "👤"
        elif role == "assistant":
            role_style = "bold green"
            role_icon = "🤖"
        else:
            role_style = "bold yellow"
            role_icon = "📝"
        
        console.print(f"{role_icon} [{role_style}]{role.capitalize()}[/{role_style}]:")
        
        # Render content (truncate if too long for display)
        if len(content) > 500:
            console.print(f"  {content[:500]}...")
            console.print(f"  [dim]({len(content) - 500} more characters)[/dim]")
        else:
            console.print(f"  {content}")
        console.print()


# ============================================================================
# Config Commands
# ============================================================================

config_app = typer.Typer(
    name="config",
    help="Manage Tracé configuration",
)
app.add_typer(config_app, name="config")


@config_app.command(name="set")
def config_set(
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            "-m",
            help="LLM model to use (e.g., 'gemini/gemini-1.5-pro', 'gpt-4o').",
        ),
    ] = None,
    api_key_env: Annotated[
        Optional[str],
        typer.Option(
            "--api-key-env",
            help="Name of environment variable containing the API key.",
        ),
    ] = None,
) -> None:
    """Configure Tracé settings.
    
    Set the LLM model and API key configuration.
    
    Examples:
        trace config set --model gemini/gemini-1.5-pro
        trace config set --model gpt-4o --api-key-env OPENAI_API_KEY
    """
    from .core.config import update_config, load_config, get_supported_models
    
    if model is None and api_key_env is None:
        console.print("[yellow]No options provided. Showing supported models:[/yellow]")
        console.print()
        
        table = Table(title="Supported Models", show_header=True, header_style="bold cyan")
        table.add_column("Model")
        table.add_column("Provider")
        table.add_column("Notes")
        
        for m in get_supported_models():
            table.add_row(m["name"], m["provider"], m["notes"])
        
        console.print(table)
        return
    
    config = update_config(model=model, api_key_env=api_key_env)
    
    console.print(Panel(
        f"[green]✓ Configuration updated[/green]\n\n"
        f"Model: [bold]{config.model}[/bold]\n"
        f"API Key Env: {config.api_key_env or '(auto-detect)'}",
        title="Config Saved",
        border_style="green",
    ))


@config_app.command(name="show")
def config_show() -> None:
    """Show current Tracé configuration."""
    from .core.config import load_config, get_config_path
    
    config = load_config()
    config_path = get_config_path()
    
    # Check API key status
    api_key = config.get_api_key()
    if api_key:
        key_status = f"[green]✓ Found[/green] ({len(api_key)} chars, ending ...{api_key[-4:]})"
    else:
        key_status = "[red]✗ Not found[/red]"
    
    console.print(Panel(
        f"Model: [bold]{config.model}[/bold]\n"
        f"API Key Env: {config.api_key_env or '(auto-detect)'}\n"
        f"API Key Status: {key_status}\n"
        f"Max Evidence Lines: {config.max_evidence_lines}\n"
        f"Max Context Chars: {config.max_context_chars}\n"
        f"\n[dim]Config file: {config_path}[/dim]",
        title="⚙️ Tracé Configuration",
        border_style="cyan",
    ))


# ============================================================================
# Review Command
# ============================================================================

@app.command()
def review(
    with_context: Annotated[
        Optional[str],
        typer.Option(
            "--with-context",
            "-c",
            help="Include specific context session ID.",
        ),
    ] = None,
    with_evidence: Annotated[
        Optional[str],
        typer.Option(
            "--with-evidence",
            "-e",
            help="Include specific evidence session ID.",
        ),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option(
            "--staged",
            "-s",
            help="Review staged changes only (for pre-commit).",
        ),
    ] = False,
    output_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output raw JSON instead of formatted display.",
        ),
    ] = False,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open",
            "-o",
            help="Open the HTML report in browser after generation.",
        ),
    ] = False,
    output_path: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            help="Custom output path for the HTML report.",
        ),
    ] = None,
) -> None:
    """Generate an evidence-based code review.
    
    Analyzes your code changes along with captured evidence (test logs,
    build output) and AI context to produce a comprehensive review.
    
    The review verifies:
    - Does the code match the stated intent?
    - Does evidence prove the code works?
    - Are there missing tests or risks?
    
    Examples:
        trace review                           # Review current changes
        trace review --staged                  # Review staged changes only
        trace review --open                    # Open HTML report in browser
        trace review --output ./my-review.html # Custom output path
    """
    from .core.analyzer import run_review, ReviewResult
    from .core.git_context import get_diff, get_staged_diff
    from .core.config import load_config
    from .core.storage import list_evidence_sessions, load_evidence
    from .output.renderer import render_review_html, save_trace, open_in_browser
    import json
    
    config = load_config()
    
    # Check API key first
    if not config.get_api_key():
        console.print("[red]Error:[/red] No API key configured.")
        console.print()
        console.print("[dim]Set one of these environment variables:[/dim]")
        console.print("  • GEMINI_API_KEY (for Gemini models)")
        console.print("  • OPENAI_API_KEY (for GPT models)")
        console.print("  • ANTHROPIC_API_KEY (for Claude models)")
        console.print()
        console.print("[dim]Or configure explicitly:[/dim]")
        console.print("  trace config set --api-key-env YOUR_ENV_VAR")
        raise typer.Exit(1)
    
    # Get diff
    console.print("[blue]Analyzing code changes...[/blue]")
    
    if staged:
        diff = get_staged_diff()
    else:
        diff = get_diff()
    
    if diff is None:
        console.print("[red]Error:[/red] Could not get git diff.")
        console.print("[dim]Make sure you're in a git repository with changes.[/dim]")
        raise typer.Exit(1)
    
    if not diff.files:
        console.print("[yellow]No changes to review.[/yellow]")
        raise typer.Exit(0)
    
    # Show what we're reviewing
    console.print(f"[dim]Found {len(diff.files)} changed files[/dim]")
    for f in diff.files[:5]:
        console.print(f"  [dim]• {f.filename} ({f.change_type})[/dim]")
    if len(diff.files) > 5:
        console.print(f"  [dim]... and {len(diff.files) - 5} more[/dim]")
    console.print()
    
    # Parse session IDs
    context_ids = [with_context] if with_context else None
    evidence_ids = [with_evidence] if with_evidence else None
    
    # Run the review
    result = run_review(
        diff=diff,
        evidence_session_ids=evidence_ids,
        context_session_ids=context_ids,
        config=config,
    )
    
    if result is None:
        console.print("[red]Review failed.[/red]")
        raise typer.Exit(1)
    
    # Output JSON if requested
    if output_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return
    
    # Gather evidence data for HTML rendering
    evidence_sessions_data = []
    if evidence_ids:
        for sid in evidence_ids:
            data = load_evidence(sid)
            if data:
                evidence_sessions_data.append(data)
    else:
        # Get recent evidence
        sessions = list_evidence_sessions()[:5]
        for session in sessions:
            data = load_evidence(session["session_id"])
            if data:
                evidence_sessions_data.append(data)
    
    # Prepare diff files for rendering
    diff_files_data = [
        {
            "filename": f.filename,
            "additions": f.additions,
            "deletions": f.deletions,
            "diff_content": f.diff_content,
        }
        for f in diff.files
    ]
    
    # Render HTML
    console.print("[blue]Generating HTML report...[/blue]")
    html_content = render_review_html(
        review_result=result.to_dict(),
        evidence_sessions=evidence_sessions_data,
        diff_files=diff_files_data,
        model=config.model,
    )
    
    # Save the trace
    if output_path:
        file_path = output_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    else:
        file_path = save_trace(html_content)
    
    console.print(f"[green]✓ Report saved:[/green] {file_path}")
    
    # Display summary in terminal
    _display_review(result)
    
    # Open in browser if requested
    if open_browser:
        console.print("[dim]Opening in browser...[/dim]")
        open_in_browser(file_path)


def _display_review(result) -> None:
    """Display a review result with Rich formatting."""
    from .core.analyzer import ReviewResult
    
    # Status styling
    status = result.status.upper()
    if status == "PASS":
        status_style = "green"
        status_icon = "✅"
    elif status == "RISK_DETECTED":
        status_style = "yellow"
        status_icon = "⚠️"
    elif status == "MISSING_EVIDENCE":
        status_style = "yellow"
        status_icon = "❓"
    else:
        status_style = "red"
        status_icon = "❌"
    
    # Header
    console.print()
    console.print(Panel(
        f"{status_icon} [{status_style} bold]{status}[/{status_style} bold]\n\n"
        f"{result.summary}",
        title="📋 Code Review",
        border_style=status_style,
    ))
    
    # Evidence Analysis
    if result.evidence_analysis:
        console.print()
        console.print(Panel(
            result.evidence_analysis,
            title="🔍 Evidence Analysis",
            border_style="blue",
        ))
    
    # File Comments
    if result.files:
        console.print()
        console.print("[bold]📁 File Comments:[/bold]")
        console.print()
        
        for file_review in result.files:
            if file_review.comments:
                console.print(f"  [bold]{file_review.filename}[/bold]")
                for comment in file_review.comments:
                    # Severity styling
                    if comment.severity == "critical":
                        sev_style = "red bold"
                        sev_icon = "🔴"
                    elif comment.severity == "high":
                        sev_style = "red"
                        sev_icon = "🟠"
                    elif comment.severity == "warning":
                        sev_style = "yellow"
                        sev_icon = "🟡"
                    else:
                        sev_style = "dim"
                        sev_icon = "🔵"
                    
                    line_info = f"L{comment.line}" if comment.line else ""
                    console.print(
                        f"    {sev_icon} [{sev_style}]{line_info}[/{sev_style}] "
                        f"{comment.message}"
                    )
                console.print()
    
    # Footer
    console.print(f"[dim]Model: {result.model_used}[/dim]")


# ============================================================================
# MCP Server Command
# ============================================================================

@app.command()
def serve() -> None:
    """Start the MCP (Model Context Protocol) server.
    
    This command starts Tracé as an MCP server on STDIO, allowing AI agents
    (Codex, Claude Desktop, Cursor, etc.) to use Tracé's capabilities.
    
    The server exposes these tools:
    - trace.run_and_capture: Execute commands and capture evidence
    - trace.get_recent_evidence: List recent evidence sessions
    - trace.generate_report: Generate HTML trace report
    
    Transport: STDIO (stdin/stdout for JSON-RPC)
    
    Example usage in agent config:
        {
            "mcpServers": {
                "trace": {
                    "command": "trace",
                    "args": ["serve"]
                }
            }
        }
    """
    from .mcp_server import main as mcp_main
    
    # Log to stderr to avoid corrupting STDIO transport
    import sys
    print("Starting Tracé MCP Server on STDIO...", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)
    
    try:
        mcp_main()
    except KeyboardInterrupt:
        print("\nTracé MCP Server stopped.", file=sys.stderr)
        raise typer.Exit(0)


if __name__ == "__main__":
    app()
