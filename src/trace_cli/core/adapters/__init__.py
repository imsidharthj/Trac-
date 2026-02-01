"""Context adapters for ingesting external AI session history."""

from .base import ContextAdapter, ContextSession
from .gemini import GeminiAdapter
from .claude import ClaudeAdapter
from .antigravity import AntigravityAdapter

__all__ = ["ContextAdapter", "ContextSession", "GeminiAdapter", "ClaudeAdapter", "AntigravityAdapter"]
