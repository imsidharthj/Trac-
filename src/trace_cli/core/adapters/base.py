"""Base classes for context adapters.

This module defines the abstract interface that all context adapters must implement.
Adapters are responsible for ingesting external AI session history from various sources
(Gemini, Claude, etc.) and converting them into a unified format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ContextMessage:
    """A single message in a context session."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSession:
    """A context session containing messages from an AI conversation.
    
    This is the unified format that all adapters produce.
    """
    session_id: str
    source: str  # "gemini", "claude", "manual", etc.
    messages: list[ContextMessage]
    title: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "source": self.source,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "metadata": msg.metadata,
                }
                for msg in self.messages
            ],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextSession":
        """Create from dictionary."""
        messages = [
            ContextMessage(
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.fromisoformat(msg["timestamp"]) if msg.get("timestamp") else None,
                metadata=msg.get("metadata", {}),
            )
            for msg in data.get("messages", [])
        ]
        return cls(
            session_id=data["session_id"],
            source=data["source"],
            messages=messages,
            title=data.get("title"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            metadata=data.get("metadata", {}),
        )
    
    def get_summary(self, max_length: int = 200) -> str:
        """Get a brief summary of the session content."""
        if not self.messages:
            return "(empty session)"
        
        # Get first user message as summary
        for msg in self.messages:
            if msg.role == "user" and msg.content.strip():
                content = msg.content.strip()
                if len(content) > max_length:
                    return content[:max_length - 3] + "..."
                return content
        
        # Fallback to first message
        content = self.messages[0].content.strip()
        if len(content) > max_length:
            return content[:max_length - 3] + "..."
        return content


class ContextAdapter(ABC):
    """Abstract base class for context adapters.
    
    Each adapter is responsible for:
    1. Reading data from a specific source (Gemini, Claude, etc.)
    2. Parsing the data into ContextMessage objects
    3. Applying redaction to remove sensitive data
    4. Returning a unified ContextSession
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the adapter name (e.g., 'gemini', 'claude')."""
        ...
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a human-readable description."""
        ...
    
    @abstractmethod
    def ingest_text(self, text: str) -> ContextSession:
        """Ingest context from raw text (e.g., pasted content).
        
        Args:
            text: Raw text content to parse.
        
        Returns:
            A ContextSession with parsed messages.
        """
        ...
    
    @abstractmethod
    def ingest_file(self, file_path: str) -> ContextSession:
        """Ingest context from a file.
        
        Args:
            file_path: Path to the file to import.
        
        Returns:
            A ContextSession with parsed messages.
        """
        ...
    
    def supports_auto_discovery(self) -> bool:
        """Whether this adapter can auto-discover sessions.
        
        Override to return True if the adapter can find sessions
        automatically (e.g., by reading local CLI history).
        """
        return False
    
    def discover_sessions(self) -> list[str]:
        """Discover available sessions for this source.
        
        Override if supports_auto_discovery() returns True.
        
        Returns:
            List of session identifiers that can be ingested.
        """
        return []


# Registry of available adapters
_adapters: dict[str, type[ContextAdapter]] = {}


def register_adapter(adapter_class: type[ContextAdapter]) -> type[ContextAdapter]:
    """Decorator to register an adapter class."""
    # Create a temporary instance to get the name
    # This is a bit hacky but works for our use case
    name = adapter_class.__name__.lower().replace("adapter", "")
    _adapters[name] = adapter_class
    return adapter_class


def get_adapter(name: str) -> ContextAdapter | None:
    """Get an adapter instance by name."""
    adapter_class = _adapters.get(name.lower())
    if adapter_class:
        return adapter_class()
    return None


def list_adapters() -> list[str]:
    """List all registered adapter names."""
    return list(_adapters.keys())
