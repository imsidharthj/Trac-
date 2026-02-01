"""Configuration management for Tracé CLI.

Stores user configuration in .ai/config.json including:
- LLM model selection
- API key (via environment variable reference)
- Other preferences
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from rich.console import Console

from .storage import get_ai_directory, initialize_storage

console = Console()

# Default configuration values
DEFAULT_MODEL = "gemini/gemini-1.5-pro"
CONFIG_FILE = "config.json"


@dataclass
class TraceConfig:
    """Configuration for Tracé CLI."""
    model: str = DEFAULT_MODEL
    api_key_env: str = ""  # Name of environment variable containing API key
    max_evidence_lines: int = 200
    max_context_chars: int = 10000
    max_diff_chars: int = 50000
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceConfig":
        """Create from dictionary."""
        return cls(
            model=data.get("model", DEFAULT_MODEL),
            api_key_env=data.get("api_key_env", ""),
            max_evidence_lines=data.get("max_evidence_lines", 200),
            max_context_chars=data.get("max_context_chars", 10000),
            max_diff_chars=data.get("max_diff_chars", 50000),
        )
    
    def get_api_key(self) -> str | None:
        """Get the API key from environment variable.
        
        Returns:
            The API key or None if not configured.
        """
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        
        # Try common environment variable names
        for env_var in [
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "LITELLM_API_KEY",
        ]:
            key = os.environ.get(env_var)
            if key:
                return key
        
        return None


def get_config_path(base_path: Path | None = None) -> Path:
    """Get the path to the config file."""
    ai_dir = get_ai_directory(base_path)
    return ai_dir / CONFIG_FILE


def load_config(base_path: Path | None = None) -> TraceConfig:
    """Load configuration from .ai/config.json.
    
    Returns default configuration if file doesn't exist.
    """
    config_path = get_config_path(base_path)
    
    if not config_path.exists():
        return TraceConfig()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return TraceConfig.from_dict(data)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[yellow]Warning: Could not load config: {e}[/yellow]")
        return TraceConfig()


def save_config(config: TraceConfig, base_path: Path | None = None) -> Path:
    """Save configuration to .ai/config.json.
    
    Returns:
        Path to the saved config file.
    """
    initialize_storage(base_path)
    config_path = get_config_path(base_path)
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
    
    return config_path


def update_config(
    model: str | None = None,
    api_key_env: str | None = None,
    base_path: Path | None = None,
) -> TraceConfig:
    """Update specific configuration values.
    
    Args:
        model: LLM model to use (e.g., "gemini/gemini-1.5-pro").
        api_key_env: Name of environment variable containing API key.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        Updated configuration.
    """
    config = load_config(base_path)
    
    if model is not None:
        config.model = model
    if api_key_env is not None:
        config.api_key_env = api_key_env
    
    save_config(config, base_path)
    return config


def get_supported_models() -> list[dict[str, str]]:
    """Get a list of supported LLM models.
    
    Returns:
        List of model info dictionaries.
    """
    return [
        {"name": "gemini/gemini-1.5-pro", "provider": "Google", "notes": "Recommended: Long context, fast"},
        {"name": "gemini/gemini-1.5-flash", "provider": "Google", "notes": "Faster, shorter context"},
        {"name": "gemini/gemini-2.0-flash", "provider": "Google", "notes": "Latest Gemini model"},
        {"name": "gpt-4o", "provider": "OpenAI", "notes": "High quality, multimodal"},
        {"name": "gpt-4o-mini", "provider": "OpenAI", "notes": "Faster, cheaper"},
        {"name": "claude-3-5-sonnet-20241022", "provider": "Anthropic", "notes": "Best for code"},
        {"name": "claude-3-5-haiku-20241022", "provider": "Anthropic", "notes": "Fast, affordable"},
    ]
