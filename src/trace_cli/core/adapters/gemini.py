"""Gemini context adapter.

This adapter ingests AI session history from Gemini CLI or exported conversations.
Since Gemini CLI stores conversations as compressed protobuf, we support:
1. Manual text paste (parsed into messages)
2. File import (text or JSON format)

All content is redacted before storage to remove sensitive data.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from ..redaction import redact_text, print_redaction_warning
from ..storage import generate_session_id
from .base import ContextAdapter, ContextMessage, ContextSession, register_adapter

console = Console()


@register_adapter
class GeminiAdapter(ContextAdapter):
    """Adapter for ingesting Gemini CLI conversation history."""
    
    def get_name(self) -> str:
        return "gemini"
    
    def get_description(self) -> str:
        return "Import context from Gemini CLI conversations"
    
    def ingest_text(self, text: str) -> ContextSession:
        """Parse pasted text into a context session.
        
        Attempts to detect conversation structure:
        - Lines starting with "User:" or "Human:" → user messages
        - Lines starting with "Assistant:" or "Gemini:" → assistant messages
        - If no structure detected, treat as single user message
        
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
        - Plain text files (parsed like text paste)
        - JSON files (expected format: {"messages": [{"role": "...", "content": "..."}]})
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
        
        # Fall back to text parsing
        return self.ingest_text(content)
    
    def _parse_conversation(self, text: str) -> list[ContextMessage]:
        """Parse conversation text into messages.
        
        Detects patterns like:
        - "User: message" / "Human: message"
        - "Assistant: message" / "Gemini: message" / "AI: message"
        - ">>> message" for user, "..." for assistant
        """
        messages: list[ContextMessage] = []
        
        # Pattern for role prefixes
        role_pattern = re.compile(
            r"^(User|Human|You|>>>|Assistant|Gemini|AI|Bot|\.\.\.)\s*[:\-]?\s*",
            re.IGNORECASE | re.MULTILINE
        )
        
        # Check if text has role markers
        if role_pattern.search(text):
            # Split by role markers
            parts = role_pattern.split(text)
            
            current_role = "user"
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                
                # Check if this part is a role marker
                lower_part = part.lower()
                if lower_part in ("user", "human", "you", ">>>"):
                    current_role = "user"
                    continue
                elif lower_part in ("assistant", "gemini", "ai", "bot", "..."):
                    current_role = "assistant"
                    continue
                
                # This is message content
                if part:
                    messages.append(ContextMessage(
                        role=current_role,
                        content=part,
                    ))
        else:
            # No structure detected - treat as single user message
            # This might be a summary or notes
            if text.strip():
                messages.append(ContextMessage(
                    role="user",
                    content=text.strip(),
                    metadata={"note": "No conversation structure detected"},
                ))
        
        return messages
    
    def _parse_json_file(self, content: str, filename: str) -> ContextSession:
        """Parse JSON format conversation."""
        data = json.loads(content)
        
        # Redact the raw content
        redacted_content = content
        for key in ("content", "text", "message"):
            # Find and redact message content in JSON
            pattern = re.compile(rf'"{key}"\s*:\s*"([^"]*)"')
            matches = pattern.findall(content)
            for match in matches:
                redaction_result = redact_text(match)
                if redaction_result.redaction_count > 0:
                    redacted_content = redacted_content.replace(match, redaction_result.redacted_text)
        
        # Re-parse the redacted content
        data = json.loads(redacted_content)
        
        messages: list[ContextMessage] = []
        
        # Handle various JSON formats
        message_list = data if isinstance(data, list) else data.get("messages", data.get("conversation", []))
        
        for msg in message_list:
            if isinstance(msg, dict):
                role = msg.get("role", msg.get("author", "user"))
                content = msg.get("content", msg.get("text", msg.get("message", "")))
                
                # Normalize role
                if role.lower() in ("human", "you"):
                    role = "user"
                elif role.lower() in ("ai", "bot", "gemini", "model"):
                    role = "assistant"
                
                if content:
                    messages.append(ContextMessage(
                        role=role,
                        content=content,
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
    
    def _extract_title(self, messages: list[ContextMessage]) -> str | None:
        """Extract a title from the first user message."""
        for msg in messages:
            if msg.role == "user" and msg.content.strip():
                # Use first 50 chars of first user message
                title = msg.content.strip()[:50]
                if len(msg.content.strip()) > 50:
                    title += "..."
                return title
        return None
