"""Redaction layer for sensitive data.

This module provides functions to scan and redact sensitive information
before storing context data. This is CRITICAL for security.

Supported patterns:
- API keys (OpenAI, Anthropic, Google, AWS, etc.)
- Bearer tokens
- Private keys (RSA, SSH, etc.)
- Passwords in URLs
- Generic secrets

All redaction is done BEFORE data is stored or sent to any LLM.
"""

import re
from dataclasses import dataclass
from typing import Callable

from rich.console import Console

console = Console()


@dataclass
class RedactionPattern:
    """A pattern for detecting and redacting sensitive data."""
    name: str
    pattern: re.Pattern
    replacement: str = "[REDACTED:{name}]"
    description: str = ""


# Comprehensive list of patterns for sensitive data
REDACTION_PATTERNS: list[RedactionPattern] = [
    # OpenAI API Keys (sk-, sk-proj-, etc.)
    RedactionPattern(
        name="OPENAI_API_KEY",
        pattern=re.compile(r"sk-(?:proj-)?[a-zA-Z0-9]{16,}"),
        description="OpenAI API key",
    ),
    # Anthropic API Keys
    RedactionPattern(
        name="ANTHROPIC_API_KEY",
        pattern=re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),
        description="Anthropic API key",
    ),
    # Google API Keys
    RedactionPattern(
        name="GOOGLE_API_KEY",
        pattern=re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        description="Google API key",
    ),
    # AWS Access Key ID
    RedactionPattern(
        name="AWS_ACCESS_KEY",
        pattern=re.compile(r"AKIA[0-9A-Z]{16}"),
        description="AWS Access Key ID",
    ),
    # AWS Secret Access Key (40 chars, base64-like)
    RedactionPattern(
        name="AWS_SECRET_KEY",
        pattern=re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
        description="AWS Secret Access Key (potential)",
    ),
    # GitHub Personal Access Tokens
    RedactionPattern(
        name="GITHUB_TOKEN",
        pattern=re.compile(r"ghp_[a-zA-Z0-9]{36}"),
        description="GitHub Personal Access Token",
    ),
    RedactionPattern(
        name="GITHUB_OAUTH",
        pattern=re.compile(r"gho_[a-zA-Z0-9]{36}"),
        description="GitHub OAuth Access Token",
    ),
    RedactionPattern(
        name="GITHUB_APP",
        pattern=re.compile(r"ghu_[a-zA-Z0-9]{36}"),
        description="GitHub App User-to-Server Token",
    ),
    # Slack Tokens
    RedactionPattern(
        name="SLACK_TOKEN",
        pattern=re.compile(r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*"),
        description="Slack Token",
    ),
    # Stripe API Keys
    RedactionPattern(
        name="STRIPE_KEY",
        pattern=re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
        description="Stripe Live API Key",
    ),
    RedactionPattern(
        name="STRIPE_TEST_KEY",
        pattern=re.compile(r"sk_test_[0-9a-zA-Z]{24,}"),
        description="Stripe Test API Key",
    ),
    # Generic Bearer Tokens
    RedactionPattern(
        name="BEARER_TOKEN",
        pattern=re.compile(r"[Bb]earer\s+[a-zA-Z0-9\-_\.]{20,}"),
        description="Bearer token in Authorization header",
    ),
    # Private Keys (PEM format)
    RedactionPattern(
        name="PRIVATE_KEY",
        pattern=re.compile(
            r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----",
            re.MULTILINE
        ),
        description="Private key (PEM format)",
    ),
    # SSH Private Keys
    RedactionPattern(
        name="SSH_PRIVATE_KEY",
        pattern=re.compile(
            r"-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+OPENSSH\s+PRIVATE\s+KEY-----",
            re.MULTILINE
        ),
        description="SSH private key",
    ),
    # Passwords in URLs
    RedactionPattern(
        name="URL_PASSWORD",
        pattern=re.compile(r"://[^:]+:([^@]+)@"),
        replacement="://[USER]:[REDACTED:PASSWORD]@",
        description="Password in URL",
    ),
    # Generic API Key patterns (key=value, KEY: value)
    RedactionPattern(
        name="GENERIC_API_KEY",
        pattern=re.compile(
            r"(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)"
            r"[\s]*[:=][\s]*['\"]?([a-zA-Z0-9\-_\.]{16,})['\"]?"
        ),
        description="Generic API key pattern",
    ),
    # Environment variable assignments with secrets
    RedactionPattern(
        name="ENV_SECRET",
        pattern=re.compile(
            r"(?i)(PASSWORD|SECRET|TOKEN|API_KEY|APIKEY|AUTH|CREDENTIAL)s?"
            r"[\s]*=[\s]*['\"]?([^\s'\"\n]{8,})['\"]?"
        ),
        description="Secret in environment variable",
    ),
    # JSON Web Tokens (JWT)
    RedactionPattern(
        name="JWT",
        pattern=re.compile(r"eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+"),
        description="JSON Web Token",
    ),
]


@dataclass
class RedactionResult:
    """Result of redaction operation."""
    original_text: str
    redacted_text: str
    redactions: list[dict[str, str]]  # List of {pattern_name, matched_value (truncated)}
    redaction_count: int


def redact_text(text: str, patterns: list[RedactionPattern] | None = None) -> RedactionResult:
    """Redact sensitive data from text.
    
    Args:
        text: The text to scan and redact.
        patterns: Optional custom patterns. Defaults to REDACTION_PATTERNS.
    
    Returns:
        RedactionResult with the redacted text and metadata.
    """
    if patterns is None:
        patterns = REDACTION_PATTERNS
    
    redacted = text
    redactions: list[dict[str, str]] = []
    
    for pattern in patterns:
        matches = pattern.pattern.findall(redacted)
        if matches:
            # Handle both simple strings and groups from findall
            for match in matches:
                if isinstance(match, tuple):
                    # Pattern has groups, use the full match area
                    match_str = match[-1] if match[-1] else match[0]
                else:
                    match_str = match
                
                # Record the redaction (truncated for privacy)
                truncated = match_str[:4] + "..." + match_str[-4:] if len(match_str) > 12 else "***"
                redactions.append({
                    "pattern": pattern.name,
                    "preview": truncated,
                })
            
            # Apply the redaction
            replacement = pattern.replacement.format(name=pattern.name)
            redacted = pattern.pattern.sub(replacement, redacted)
    
    return RedactionResult(
        original_text=text,
        redacted_text=redacted,
        redactions=redactions,
        redaction_count=len(redactions),
    )


def scan_for_secrets(text: str, patterns: list[RedactionPattern] | None = None) -> list[dict[str, str]]:
    """Scan text for secrets without redacting.
    
    Args:
        text: The text to scan.
        patterns: Optional custom patterns. Defaults to REDACTION_PATTERNS.
    
    Returns:
        List of detected secrets with pattern names and truncated previews.
    """
    if patterns is None:
        patterns = REDACTION_PATTERNS
    
    detected: list[dict[str, str]] = []
    
    for pattern in patterns:
        matches = pattern.pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                match_str = match[-1] if match[-1] else match[0]
            else:
                match_str = match
            
            truncated = match_str[:4] + "..." + match_str[-4:] if len(match_str) > 12 else "***"
            detected.append({
                "pattern": pattern.name,
                "description": pattern.description,
                "preview": truncated,
            })
    
    return detected


def print_redaction_warning(redactions: list[dict[str, str]]) -> None:
    """Print a warning about redacted content."""
    if not redactions:
        return
    
    console.print()
    console.print("[yellow]⚠ Sensitive data detected and redacted:[/yellow]")
    for r in redactions:
        console.print(f"  • {r['pattern']}: {r['preview']}")
    console.print()
