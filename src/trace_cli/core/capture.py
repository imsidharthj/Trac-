"""Command capture with real-time streaming output.

This module implements the core "Evidence Collector" functionality:
- Execute commands via subprocess
- Stream output to console in REAL-TIME (critical requirement)
- Buffer output for later storage
- Record metadata (exit code, duration, timestamps)
"""

import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .storage import generate_session_id, save_evidence, save_imported_log

console = Console()


@dataclass
class CaptureResult:
    """Result of a command capture session."""
    session_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    evidence_path: Path


def run_and_capture(
    command: str,
    base_path: Path | None = None,
    cwd: str | None = None,
    quiet: bool = False,
) -> CaptureResult:
    """Execute a command with real-time output streaming and capture.
    
    This function:
    1. Shows a header panel indicating recording has started (unless quiet)
    2. Executes the command via subprocess
    3. Streams stdout/stderr to the console IN REAL-TIME (not buffered)
    4. Captures all output for storage
    5. Shows a footer panel with results (unless quiet)
    6. Saves evidence to .ai/evidence/
    
    Args:
        command: The command string to execute.
        base_path: Base directory for .ai/ storage.
        cwd: Working directory for command execution.
        quiet: If True, suppress Rich panels and route output to stderr.
                Use this for MCP STDIO mode to avoid corrupting JSON-RPC.
    
    Returns:
        CaptureResult with all capture metadata.
    """
    session_id = generate_session_id()
    
    # Use stderr console for quiet mode (MCP STDIO compatibility)
    output_console = Console(stderr=True) if quiet else console
    
    # === HEADER: Recording indicator ===
    if not quiet:
        header = Text()
        header.append("● ", style="red bold")
        header.append("Recording", style="bold")
        header.append(f"  {command}", style="dim")
        
        output_console.print(Panel(
            header,
            border_style="red",
            padding=(0, 1),
        ))
        output_console.print()  # Spacing before command output
    
    # === EXECUTE: Real-time streaming ===
    stdout_buffer: list[str] = []
    stderr_buffer: list[str] = []
    
    start_time = time.perf_counter()
    
    try:
        # Parse command for shell execution
        # We use shell=True to support pipes, redirects, etc.
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line-buffered for real-time output
            cwd=cwd,
        )
        
        # Read stdout and stderr in real-time
        # We need to handle both streams - use select or threads
        # For simplicity and reliability, we'll use a combined approach
        import selectors
        
        selector = selectors.DefaultSelector()
        if process.stdout:
            selector.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            selector.register(process.stderr, selectors.EVENT_READ)
        
        while selector.get_map():
            events = selector.select(timeout=0.1)
            for key, _ in events:
                line = key.fileobj.readline()
                if line:
                    if key.fileobj == process.stdout:
                        # Stream to console immediately (CRITICAL: real-time)
                        # In quiet mode, stream to stderr to preserve STDIO
                        if quiet:
                            sys.stderr.write(line)
                            sys.stderr.flush()
                        else:
                            sys.stdout.write(line)
                            sys.stdout.flush()
                        stdout_buffer.append(line)
                    else:
                        # Stderr always goes to stderr
                        sys.stderr.write(line)
                        sys.stderr.flush()
                        stderr_buffer.append(line)
                else:
                    # EOF on this stream
                    selector.unregister(key.fileobj)
        
        # Wait for process to complete
        exit_code = process.wait()
        
    except FileNotFoundError:
        exit_code = 127
        error_msg = f"Command not found: {command.split()[0] if command else command}\n"
        sys.stderr.write(error_msg)
        stderr_buffer.append(error_msg)
    except Exception as e:
        exit_code = 1
        error_msg = f"Error executing command: {e}\n"
        sys.stderr.write(error_msg)
        stderr_buffer.append(error_msg)
    
    end_time = time.perf_counter()
    duration_ms = int((end_time - start_time) * 1000)
    
    # Combine buffers
    stdout_str = "".join(stdout_buffer)
    stderr_str = "".join(stderr_buffer)
    
    # === FOOTER: Results indicator ===
    if not quiet:
        output_console.print()  # Spacing after command output
        
        # Build footer with status
        footer = Text()
        if exit_code == 0:
            footer.append("✓ ", style="green bold")
            footer.append("Complete", style="green")
        else:
            footer.append("✗ ", style="red bold")
            footer.append(f"Exit {exit_code}", style="red")
        
        footer.append(f"  │  {duration_ms}ms", style="dim")
        footer.append(f"  │  Session: {session_id}", style="dim")
        
        footer_style = "green" if exit_code == 0 else "red"
        output_console.print(Panel(
            footer,
            border_style=footer_style,
            padding=(0, 1),
        ))
    
    # === SAVE: Evidence to .ai/ ===
    evidence_path = save_evidence(
        session_id=session_id,
        command=command,
        exit_code=exit_code,
        stdout=stdout_str,
        stderr=stderr_str,
        duration_ms=duration_ms,
        base_path=base_path,
    )
    
    if not quiet:
        output_console.print(f"[dim]Evidence saved: {evidence_path}[/dim]")
    
    return CaptureResult(
        session_id=session_id,
        command=command,
        exit_code=exit_code,
        stdout=stdout_str,
        stderr=stderr_str,
        duration_ms=duration_ms,
        evidence_path=evidence_path,
    )


def capture_log_file(
    log_path: str | Path,
    base_path: Path | None = None,
) -> CaptureResult:
    """Import an existing log file as evidence.
    
    Args:
        log_path: Path to the log file to import.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        CaptureResult with import metadata.
    """
    session_id = generate_session_id()
    log_path = Path(log_path)
    
    if not log_path.exists():
        console.print(f"[red]Error:[/red] Log file not found: {log_path}")
        raise FileNotFoundError(f"Log file not found: {log_path}")
    
    # Read the log file
    content = log_path.read_text(encoding="utf-8", errors="replace")
    
    # Show import status
    console.print(Panel(
        f"[blue]Importing[/blue] {log_path.name} ({len(content)} bytes)",
        border_style="blue",
        padding=(0, 1),
    ))
    
    # Save as evidence
    evidence_path = save_imported_log(
        session_id=session_id,
        source_file=str(log_path.absolute()),
        content=content,
        base_path=base_path,
    )
    
    console.print(f"[green]✓[/green] Imported as session: {session_id}")
    console.print(f"[dim]Evidence saved: {evidence_path}[/dim]")
    
    return CaptureResult(
        session_id=session_id,
        command=f"import:{log_path}",
        exit_code=0,
        stdout=content,
        stderr="",
        duration_ms=0,
        evidence_path=evidence_path,
    )
