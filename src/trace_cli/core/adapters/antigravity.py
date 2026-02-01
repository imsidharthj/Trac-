"""Antigravity context adapter.

This adapter ingests AI session history from Antigravity (Google's agentic coding assistant).
Antigravity stores conversations in ~/.gemini/antigravity/ in protobuf format.

Since protobuf parsing is complex, we support:
1. Auto-discovery by scanning for project-relevant conversations
2. Reading brain/artifact files (task.md, walkthrough.md, etc.)
3. File import (text or JSON format)

All content is redacted before storage to remove sensitive data.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from ..redaction import redact_text, print_redaction_warning
from ..storage import generate_session_id
from .base import ContextAdapter, ContextMessage, ContextSession, register_adapter

console = Console()

# Antigravity storage locations
ANTIGRAVITY_BASE = Path.home() / ".gemini" / "antigravity"
CONVERSATIONS_DIR = ANTIGRAVITY_BASE / "conversations"
BRAIN_DIR = ANTIGRAVITY_BASE / "brain"


@register_adapter
class AntigravityAdapter(ContextAdapter):
    """Adapter for ingesting Antigravity coder conversation history."""
    
    def get_name(self) -> str:
        return "antigravity"
    
    def get_description(self) -> str:
        return "Import context from Antigravity (Google agentic coder) sessions"
    
    def supports_auto_discovery(self) -> bool:
        """Antigravity can auto-discover relevant conversations."""
        return True
    
    def discover_sessions(self) -> list[str]:
        """Discover available Antigravity sessions for the current project.
        
        Searches for conversations that mention the current project directory.
        """
        sessions = []
        
        # Get current working directory name as project identifier
        cwd = Path.cwd()
        project_name = cwd.name
        
        # Search brain directories for project matches
        if BRAIN_DIR.exists():
            for uuid_dir in BRAIN_DIR.iterdir():
                if uuid_dir.is_dir():
                    # Check if any file in this brain folder mentions our project
                    for meta_file in uuid_dir.glob("*"):
                        if self._scan_file_for_keyword(meta_file, project_name):
                            sessions.append(uuid_dir.name)
                            break
        
        return sessions
    
    def ingest_text(self, text: str) -> ContextSession:
        """Parse pasted text into a context session.
        
        Attempts to detect conversation structure from Antigravity format.
        All content is redacted before storage.
        """
        # Redact sensitive data first
        redaction_result = redact_text(text)
        if redaction_result.redaction_count > 0:
            print_redaction_warning(redaction_result.redactions)
        
        redacted_text = redaction_result.redacted_text
        messages = self._parse_conversation(redacted_text)
        
        session_id = generate_session_id()
        return ContextSession(
            session_id=session_id,
            source=self.get_name(),
            messages=messages,
            title=self._extract_title(messages),
            created_at=datetime.now(timezone.utc),
            metadata={
                "ingestion_method": "text_paste",
                "redactions": redaction_result.redaction_count,
            },
        )
    
    def ingest_file(self, file_path: str) -> ContextSession:
        """Import context from a file.
        
        Supports:
        - Plain text files (task.md, walkthrough.md, etc.)
        - JSON files
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        content = path.read_text(encoding="utf-8", errors="replace")
        
        # Try JSON first
        if path.suffix.lower() == ".json":
            try:
                return self._parse_json_file(content, path.name)
            except json.JSONDecodeError:
                console.print("[yellow]Warning: JSON parsing failed, treating as plain text[/yellow]")
        
        # For markdown files (task.md, walkthrough.md), parse as artifact
        if path.suffix.lower() == ".md":
            return self._parse_markdown_artifact(content, path.name)
        
        # Fall back to text parsing
        return self.ingest_text(content)
    
    def ingest_session(self, session_uuid: str) -> ContextSession:
        """Ingest a discovered Antigravity session by UUID.
        
        Reads from the brain/ directory to get task.md, walkthrough.md, etc.
        """
        brain_path = BRAIN_DIR / session_uuid
        
        if not brain_path.exists():
            raise FileNotFoundError(f"Session not found: {session_uuid}")
        
        messages: list[ContextMessage] = []
        artifacts_found = []
        
        # Read all markdown files in the brain folder
        for artifact_file in sorted(brain_path.glob("*.md")):
            try:
                content = artifact_file.read_text(encoding="utf-8", errors="replace")
                
                # Redact content
                redaction_result = redact_text(content)
                redacted_content = redaction_result.redacted_text
                
                # Add as assistant message with artifact context
                messages.append(ContextMessage(
                    role="assistant",
                    content=f"[Artifact: {artifact_file.name}]\n\n{redacted_content}",
                    metadata={
                        "artifact_name": artifact_file.name,
                        "artifact_type": "markdown",
                    },
                ))
                artifacts_found.append(artifact_file.name)
            except Exception:
                pass
        
        if not messages:
            raise ValueError(f"No readable artifacts found in session: {session_uuid}")
        
        session_id = generate_session_id()
        return ContextSession(
            session_id=session_id,
            source=self.get_name(),
            messages=messages,
            title=f"Antigravity session: {session_uuid[:8]}",
            created_at=datetime.now(timezone.utc),
            metadata={
                "ingestion_method": "auto_discovery",
                "antigravity_uuid": session_uuid,
                "artifacts": artifacts_found,
            },
        )
    
    def _scan_file_for_keyword(self, filepath: Path, keyword: str) -> bool:
        """Check if a file contains a keyword (binary-safe)."""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
                # Try UTF-8 encoding
                if keyword.encode('utf-8') in content:
                    return True
                # Try UTF-16 as fallback
                if keyword.encode('utf-16-le') in content:
                    return True
        except Exception:
            pass
        return False
    
    def _parse_conversation(self, text: str) -> list[ContextMessage]:
        """Parse conversation text into messages."""
        messages: list[ContextMessage] = []
        
        # Try to detect Antigravity-style patterns
        # Antigravity uses task boundaries and artifact updates
        
        # Pattern for task boundaries
        task_pattern = re.compile(
            r"(?:Task|Step|Phase)\s*[:\-]?\s*(.+?)(?:\n|$)",
            re.IGNORECASE
        )
        
        # Pattern for user/assistant turns
        role_pattern = re.compile(
            r"^(User|Human|You|Assistant|AI|Agent|Antigravity)\s*[:\-]?\s*",
            re.IGNORECASE | re.MULTILINE
        )
        
        if role_pattern.search(text):
            parts = role_pattern.split(text)
            current_role = "user"
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                lower_part = part.lower()
                if lower_part in ("user", "human", "you"):
                    current_role = "user"
                    continue
                elif lower_part in ("assistant", "ai", "agent", "antigravity"):
                    current_role = "assistant"
                    continue
                
                if part:
                    messages.append(ContextMessage(
                        role=current_role,
                        content=part,
                    ))
        else:
            # No structure detected - treat as context/notes
            if text.strip():
                messages.append(ContextMessage(
                    role="assistant",
                    content=text.strip(),
                    metadata={"note": "Antigravity context without structure"},
                ))
        
        return messages
    
    def _parse_json_file(self, content: str, filename: str) -> ContextSession:
        """Parse JSON format conversation."""
        data = json.loads(content)
        
        # Redact content in JSON
        redacted_content = content
        for key in ("content", "text", "message"):
            pattern = re.compile(rf'"{key}"\s*:\s*"([^"]*)"')
            matches = pattern.findall(content)
            for match in matches:
                redaction_result = redact_text(match)
                if redaction_result.redaction_count > 0:
                    redacted_content = redacted_content.replace(match, redaction_result.redacted_text)
        
        data = json.loads(redacted_content)
        messages: list[ContextMessage] = []
        
        message_list = data if isinstance(data, list) else data.get("messages", data.get("conversation", []))
        
        for msg in message_list:
            if isinstance(msg, dict):
                role = msg.get("role", msg.get("author", "assistant"))
                msg_content = msg.get("content", msg.get("text", msg.get("message", "")))
                
                if role.lower() in ("human", "user", "you"):
                    role = "user"
                else:
                    role = "assistant"
                
                if msg_content:
                    messages.append(ContextMessage(
                        role=role,
                        content=msg_content,
                    ))
        
        session_id = generate_session_id()
        return ContextSession(
            session_id=session_id,
            source=self.get_name(),
            messages=messages,
            title=data.get("title", filename),
            created_at=datetime.now(timezone.utc),
            metadata={
                "ingestion_method": "json_file",
                "source_file": filename,
            },
        )
    
    def _parse_markdown_artifact(self, content: str, filename: str) -> ContextSession:
        """Parse a markdown artifact file."""
        # Redact first
        redaction_result = redact_text(content)
        redacted_content = redaction_result.redacted_text
        
        # Extract title from first heading
        title_match = re.search(r'^#\s+(.+?)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else filename
        
        messages = [ContextMessage(
            role="assistant",
            content=f"[Artifact: {filename}]\n\n{redacted_content}",
            metadata={"artifact_name": filename},
        )]
        
        session_id = generate_session_id()
        return ContextSession(
            session_id=session_id,
            source=self.get_name(),
            messages=messages,
            title=title,
            created_at=datetime.now(timezone.utc),
            metadata={
                "ingestion_method": "markdown_artifact",
                "source_file": filename,
                "redactions": redaction_result.redaction_count,
            },
        )
    
    def _extract_title(self, messages: list[ContextMessage]) -> str | None:
        """Extract a title from messages."""
        for msg in messages:
            if msg.content.strip():
                title = msg.content.strip()[:50]
                if len(msg.content.strip()) > 50:
                    title += "..."
                return title
        return None
