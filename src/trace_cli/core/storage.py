"""Storage management for the .ai/ directory and evidence sessions."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()

# Default storage directory name
AI_DIR_NAME = ".ai"
EVIDENCE_DIR = "evidence"
CONTEXT_DIR = "context"


def get_ai_directory(base_path: Path | None = None) -> Path:
    """Get the .ai/ directory path, creating it if necessary.
    
    Args:
        base_path: The base directory to create .ai/ in. Defaults to current directory.
    
    Returns:
        Path to the .ai/ directory.
    """
    if base_path is None:
        base_path = Path.cwd()
    
    ai_dir = base_path / AI_DIR_NAME
    return ai_dir


def initialize_storage(base_path: Path | None = None) -> Path:
    """Initialize the .ai/ directory structure.
    
    Creates:
        .ai/
        ├── evidence/    # Captured command outputs
        └── context/     # Ingested AI session history
    
    Args:
        base_path: The base directory to create .ai/ in. Defaults to current directory.
    
    Returns:
        Path to the .ai/ directory.
    """
    ai_dir = get_ai_directory(base_path)
    
    # Create main directory and subdirectories
    evidence_dir = ai_dir / EVIDENCE_DIR
    context_dir = ai_dir / CONTEXT_DIR
    
    evidence_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)
    
    return ai_dir


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())[:8]  # Short UUID for readability


def get_timestamp() -> str:
    """Get current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def save_evidence(
    session_id: str,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: int,
    metadata: dict[str, Any] | None = None,
    base_path: Path | None = None,
) -> Path:
    """Save an evidence session to JSON.
    
    Args:
        session_id: Unique session identifier.
        command: The command that was executed.
        exit_code: Process exit code.
        stdout: Captured standard output.
        stderr: Captured standard error.
        duration_ms: Execution duration in milliseconds.
        metadata: Additional metadata to include.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        Path to the saved JSON file.
    """
    ai_dir = initialize_storage(base_path)
    evidence_dir = ai_dir / EVIDENCE_DIR
    
    evidence = {
        "session_id": session_id,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timestamp": get_timestamp(),
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }
    
    file_path = evidence_dir / f"session_{session_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    
    return file_path


def save_imported_log(
    session_id: str,
    source_file: str,
    content: str,
    base_path: Path | None = None,
) -> Path:
    """Save an imported log file as evidence.
    
    Args:
        session_id: Unique session identifier.
        source_file: Path to the original log file.
        content: The log file content.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        Path to the saved JSON file.
    """
    ai_dir = initialize_storage(base_path)
    evidence_dir = ai_dir / EVIDENCE_DIR
    
    evidence = {
        "session_id": session_id,
        "type": "imported_log",
        "source_file": source_file,
        "content": content,
        "timestamp": get_timestamp(),
        "metadata": {
            "imported": True,
        },
    }
    
    file_path = evidence_dir / f"log_{session_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    
    return file_path


def list_evidence_sessions(base_path: Path | None = None) -> list[dict[str, Any]]:
    """List all evidence sessions.
    
    Args:
        base_path: Base directory for .ai/ storage.
    
    Returns:
        List of evidence session metadata.
    """
    ai_dir = get_ai_directory(base_path)
    evidence_dir = ai_dir / EVIDENCE_DIR
    
    if not evidence_dir.exists():
        return []
    
    sessions = []
    for file_path in evidence_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Return summary info only
                sessions.append({
                    "session_id": data.get("session_id"),
                    "command": data.get("command", data.get("source_file", "N/A")),
                    "exit_code": data.get("exit_code"),
                    "timestamp": data.get("timestamp"),
                    "type": data.get("type", "command"),
                    "file": str(file_path),
                })
        except (json.JSONDecodeError, OSError):
            continue
    
    # Sort by timestamp, newest first
    sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return sessions


def load_evidence(session_id: str, base_path: Path | None = None) -> dict[str, Any] | None:
    """Load a specific evidence session.
    
    Args:
        session_id: The session ID to load.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        The evidence data or None if not found.
    """
    ai_dir = get_ai_directory(base_path)
    evidence_dir = ai_dir / EVIDENCE_DIR
    
    if not evidence_dir.exists():
        return None
    
    # Try both naming patterns
    for pattern in [f"session_{session_id}.json", f"log_{session_id}.json"]:
        file_path = evidence_dir / pattern
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    
    return None


# ============================================================================
# Context Storage Functions
# ============================================================================

def save_context(
    context_data: dict[str, Any],
    base_path: Path | None = None,
) -> Path:
    """Save a context session to JSON.
    
    Args:
        context_data: The context session data (from ContextSession.to_dict()).
        base_path: Base directory for .ai/ storage.
    
    Returns:
        Path to the saved JSON file.
    """
    ai_dir = initialize_storage(base_path)
    context_dir = ai_dir / CONTEXT_DIR
    
    session_id = context_data.get("session_id", generate_session_id())
    file_path = context_dir / f"context_{session_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(context_data, f, indent=2, ensure_ascii=False)
    
    return file_path


def list_context_sessions(base_path: Path | None = None) -> list[dict[str, Any]]:
    """List all context sessions.
    
    Args:
        base_path: Base directory for .ai/ storage.
    
    Returns:
        List of context session metadata.
    """
    ai_dir = get_ai_directory(base_path)
    context_dir = ai_dir / CONTEXT_DIR
    
    if not context_dir.exists():
        return []
    
    sessions = []
    for file_path in context_dir.glob("context_*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Return summary info only
                messages = data.get("messages", [])
                sessions.append({
                    "session_id": data.get("session_id"),
                    "source": data.get("source", "unknown"),
                    "title": data.get("title"),
                    "message_count": len(messages),
                    "created_at": data.get("created_at"),
                    "file": str(file_path),
                })
        except (json.JSONDecodeError, OSError):
            continue
    
    # Sort by created_at, newest first
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return sessions


def load_context(session_id: str, base_path: Path | None = None) -> dict[str, Any] | None:
    """Load a specific context session.
    
    Args:
        session_id: The session ID to load.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        The context data or None if not found.
    """
    ai_dir = get_ai_directory(base_path)
    context_dir = ai_dir / CONTEXT_DIR
    
    if not context_dir.exists():
        return None
    
    file_path = context_dir / f"context_{session_id}.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    return None
