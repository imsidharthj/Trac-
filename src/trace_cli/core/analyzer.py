"""The Review Brain — LLM-powered code analysis.

This module is the core of Tracé's evidence-based review system.
It combines:
- Code (Git Diff)
- Proof (Captured Evidence/Logs)
- Reasoning (AI Context History)

Into a structured, verifiable code review.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from .config import load_config, TraceConfig
from .git_context import GitDiff, map_evidence_to_files
from .storage import list_evidence_sessions, load_evidence, load_context

console = Console()


# ============================================================================
# Review Output Schema
# ============================================================================

@dataclass
class FileComment:
    """A comment on a specific line in a file."""
    line: int | None
    severity: str  # "info", "warning", "high", "critical"
    message: str


@dataclass
class FileReview:
    """Review for a single file."""
    filename: str
    comments: list[FileComment] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Complete review result from the analyzer."""
    summary: str
    status: str  # "PASS", "risk_detected", "missing_evidence"
    evidence_analysis: str
    files: list[FileReview] = field(default_factory=list)
    raw_response: str = ""
    model_used: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary": self.summary,
            "status": self.status,
            "evidence_analysis": self.evidence_analysis,
            "files": [
                {
                    "filename": f.filename,
                    "comments": [
                        {"line": c.line, "severity": c.severity, "message": c.message}
                        for c in f.comments
                    ]
                }
                for f in self.files
            ],
            "model_used": self.model_used,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewResult":
        """Create from dictionary."""
        files = []
        for f_data in data.get("files", []):
            comments = [
                FileComment(
                    line=c.get("line"),
                    severity=c.get("severity", "info"),
                    message=c.get("message", ""),
                )
                for c in f_data.get("comments", [])
            ]
            files.append(FileReview(
                filename=f_data.get("filename", ""),
                comments=comments,
            ))
        
        return cls(
            summary=data.get("summary", ""),
            status=data.get("status", "unknown"),
            evidence_analysis=data.get("evidence_analysis", ""),
            files=files,
            model_used=data.get("model_used", ""),
        )


# ============================================================================
# Evidence Processing
# ============================================================================

def truncate_evidence(
    content: str,
    max_lines: int = 200,
    preserve_keywords: list[str] | None = None,
) -> str:
    """Intelligently truncate evidence/log content.
    
    Strategy:
    1. Keep lines containing important keywords (errors, failures)
    2. Keep the last N lines
    3. Prefix with truncation notice
    
    Args:
        content: The log content to truncate.
        max_lines: Maximum lines to keep.
        preserve_keywords: Keywords that mark important lines.
    
    Returns:
        Truncated content.
    """
    if preserve_keywords is None:
        preserve_keywords = [
            "error", "fail", "exception", "traceback", "warn",
            "assert", "panic", "fatal", "critical", "denied",
        ]
    
    lines = content.split("\n")
    
    if len(lines) <= max_lines:
        return content
    
    # Find important lines (containing keywords)
    important_lines: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw in line_lower for kw in preserve_keywords):
            important_lines.append((i, line))
    
    # Take last N lines
    tail_start = max(0, len(lines) - max_lines // 2)
    tail_lines = lines[tail_start:]
    
    # Combine: important lines + tail (deduplicated)
    result_lines: list[str] = []
    seen_indices = set()
    
    # Add important lines first (limited)
    for i, line in important_lines[:max_lines // 3]:
        if i not in seen_indices:
            result_lines.append(f"[line {i+1}] {line}")
            seen_indices.add(i)
    
    if important_lines:
        result_lines.append("...")
        result_lines.append(f"[... {len(lines) - len(result_lines) - len(tail_lines)} lines omitted ...]")
        result_lines.append("...")
    
    # Add tail lines
    for i, line in enumerate(tail_lines):
        original_idx = tail_start + i
        if original_idx not in seen_indices:
            result_lines.append(line)
    
    truncation_notice = f"[TRUNCATED: Original {len(lines)} lines → {len(result_lines)} lines]\n\n"
    return truncation_notice + "\n".join(result_lines)


def gather_evidence(
    session_ids: list[str] | None = None,
    max_chars: int = 50000,
) -> str:
    """Gather evidence from captured sessions.
    
    Args:
        session_ids: Specific session IDs to include. If None, uses recent sessions.
        max_chars: Maximum characters to include.
    
    Returns:
        Combined evidence string.
    """
    if session_ids is None:
        # Get recent evidence sessions
        sessions = list_evidence_sessions()[:5]  # Last 5 sessions
        session_ids = [s["session_id"] for s in sessions]
    
    evidence_parts: list[str] = []
    total_chars = 0
    
    for sid in session_ids:
        data = load_evidence(sid)
        if data:
            command = data.get("command", "unknown")
            exit_code = data.get("exit_code", "?")
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            
            # Format this evidence block
            block = f"""
=== Evidence: {command} ===
Exit Code: {exit_code}
{truncate_evidence(stdout + stderr)}
"""
            if total_chars + len(block) > max_chars:
                break
            
            evidence_parts.append(block)
            total_chars += len(block)
    
    if not evidence_parts:
        return "[No evidence captured. Run 'trace run <command>' to capture evidence.]"
    
    return "\n".join(evidence_parts)


def gather_context(
    session_ids: list[str] | None = None,
    max_chars: int = 10000,
) -> str:
    """Gather context from ingested AI sessions.
    
    Args:
        session_ids: Specific session IDs to include.
        max_chars: Maximum characters to include.
    
    Returns:
        Combined context string.
    """
    from .storage import list_context_sessions
    
    if session_ids is None:
        sessions = list_context_sessions()[:3]
        session_ids = [s["session_id"] for s in sessions]
    
    context_parts: list[str] = []
    total_chars = 0
    
    for sid in session_ids:
        data = load_context(sid)
        if data:
            messages = data.get("messages", [])
            source = data.get("source", "unknown")
            
            # Format messages
            msg_texts = []
            for msg in messages[-10:]:  # Last 10 messages
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."
                msg_texts.append(f"{role.upper()}: {content}")
            
            block = f"""
=== Context from {source} (Session: {sid}) ===
{chr(10).join(msg_texts)}
"""
            if total_chars + len(block) > max_chars:
                break
            
            context_parts.append(block)
            total_chars += len(block)
    
    if not context_parts:
        return "[No context ingested. Run 'trace context add' to add AI session history.]"
    
    return "\n".join(context_parts)


# ============================================================================
# Prompt Building
# ============================================================================

SYSTEM_PROMPT = """You are a Senior Software Architect acting as a "Witness" code reviewer.

Unlike traditional code reviewers, you don't just read code — you VERIFY claims with evidence.

Your review process:
1. Read the INTENT (context from developer's AI chat) to understand WHY the change was made
2. Check the PROOF (captured command outputs, test logs) to verify claims
3. Analyze the CODE (git diff) with this evidence in mind

You MUST return a valid JSON object with this exact structure:
{
  "summary": "High-level summary of the change and your assessment",
  "status": "PASS" | "risk_detected" | "missing_evidence",
  "evidence_analysis": "Your analysis of what the evidence shows (tests passed/failed, commands run, etc.)",
  "files": [
    {
      "filename": "path/to/file.py",
      "comments": [
        {"line": 42, "severity": "high", "message": "Specific issue or observation"}
      ]
    }
  ]
}

Severity levels:
- "info": Observations, suggestions, style notes
- "warning": Potential issues, should be reviewed
- "high": Likely bugs, security concerns, missing tests
- "critical": Must fix before merging

Status meanings:
- "PASS": Evidence supports the change, no critical issues
- "risk_detected": Evidence shows potential problems or the code has issues
- "missing_evidence": Cannot verify claims (e.g., "tests pass" but no test output captured)

IMPORTANT: Always output valid JSON only. No markdown, no explanations outside the JSON."""


def build_review_prompt(
    diff: GitDiff,
    evidence: str,
    context: str,
) -> list[dict[str, str]]:
    """Build the evidence-first prompt for the LLM.
    
    Args:
        diff: The git diff to review.
        evidence: Captured evidence content.
        context: Ingested AI context.
    
    Returns:
        List of messages for the LLM.
    """
    # Build file list
    file_list = "\n".join([
        f"  - {f.filename} ({f.change_type}: +{f.additions}/-{f.deletions})"
        for f in diff.files
    ])
    
    # Build the user message with evidence-first structure
    user_message = f"""Please review this code change.

## INPUT 1: THE INTENT (Context)
This explains WHY the developer made this change. Use this to understand their reasoning.

{context}

---

## INPUT 2: THE PROOF (Evidence)
These are captured command outputs (test runs, builds, etc.). Check if tests passed/failed.

{evidence}

---

## INPUT 3: THE CODE (Diff)

Files changed:
{file_list}

```diff
{diff.raw_diff[:50000]}
```

---

## YOUR TASK

1. Does the code match the stated intent?
2. Does the evidence PROVE the code works? (Look for test results, error messages)
3. Identify specific risks or missing evidence (e.g., "Changed auth logic but no auth tests run")

Return your review as a JSON object following the schema exactly."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


# ============================================================================
# LLM Integration
# ============================================================================

def call_llm(
    messages: list[dict[str, str]],
    config: TraceConfig,
) -> str | None:
    """Call the LLM via LiteLLM.
    
    Args:
        messages: List of message dicts.
        config: Trace configuration.
    
    Returns:
        LLM response text or None on error.
    """
    try:
        import litellm
        
        # Get API key
        api_key = config.get_api_key()
        if not api_key:
            console.print("[red]Error:[/red] No API key configured.")
            console.print("[dim]Set an environment variable (GEMINI_API_KEY, OPENAI_API_KEY, etc.)")
            console.print("or run: trace config set --api-key-env YOUR_ENV_VAR[/dim]")
            return None
        
        # Configure litellm
        model = config.model
        
        # Set appropriate API key based on model
        if "gemini" in model.lower() or "google" in model.lower():
            litellm.api_key = api_key
        elif "gpt" in model.lower() or "openai" in model.lower():
            import os
            os.environ["OPENAI_API_KEY"] = api_key
        elif "claude" in model.lower() or "anthropic" in model.lower():
            import os
            os.environ["ANTHROPIC_API_KEY"] = api_key
        
        # Call the LLM
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.1,  # Low temperature for consistent output
            response_format={"type": "json_object"} if "gpt" in model.lower() else None,
        )
        
        return response.choices[0].message.content
    
    except ImportError:
        console.print("[red]Error:[/red] LiteLLM is not installed. Run: uv add litellm")
        return None
    except Exception as e:
        console.print(f"[red]LLM Error:[/red] {e}")
        return None


def parse_review_response(response: str) -> ReviewResult | None:
    """Parse the LLM response into a ReviewResult.
    
    Args:
        response: Raw LLM response text.
    
    Returns:
        ReviewResult or None on parse error.
    """
    try:
        # Try to extract JSON from the response
        # Sometimes LLMs wrap JSON in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response
        
        data = json.loads(json_str)
        return ReviewResult.from_dict(data)
    
    except json.JSONDecodeError as e:
        console.print(f"[yellow]Warning: Could not parse LLM response as JSON: {e}[/yellow]")
        # Return a basic result with the raw response
        return ReviewResult(
            summary="Could not parse structured response",
            status="error",
            evidence_analysis=response[:500] if response else "",
            raw_response=response,
        )


# ============================================================================
# Main Review Function
# ============================================================================

def run_review(
    diff: GitDiff | None = None,
    evidence_session_ids: list[str] | None = None,
    context_session_ids: list[str] | None = None,
    config: TraceConfig | None = None,
) -> ReviewResult | None:
    """Run an evidence-based code review.
    
    Args:
        diff: Git diff to review. Auto-detected if None.
        evidence_session_ids: Specific evidence sessions to include.
        context_session_ids: Specific context sessions to include.
        config: Configuration. Loaded if None.
    
    Returns:
        ReviewResult or None on error.
    """
    if config is None:
        config = load_config()
    
    # Get diff if not provided
    if diff is None:
        from .git_context import get_diff
        diff = get_diff()
        if diff is None:
            console.print("[red]Error:[/red] Could not get git diff.")
            console.print("[dim]Make sure you're in a git repository with changes.[/dim]")
            return None
    
    if not diff.files:
        console.print("[yellow]No changes detected in diff.[/yellow]")
        return ReviewResult(
            summary="No changes to review",
            status="PASS",
            evidence_analysis="No files changed.",
            model_used=config.model,
        )
    
    # Gather evidence
    console.print("[dim]Gathering evidence...[/dim]")
    evidence = gather_evidence(evidence_session_ids, max_chars=config.max_evidence_lines * 100)
    
    # Gather context
    console.print("[dim]Gathering context...[/dim]")
    context = gather_context(context_session_ids, max_chars=config.max_context_chars)
    
    # Map evidence to files for relevance
    changed_files = diff.get_changed_filenames()
    relevance = map_evidence_to_files(evidence, changed_files)
    
    # Build prompt
    console.print("[dim]Building review prompt...[/dim]")
    messages = build_review_prompt(diff, evidence, context)
    
    # Call LLM
    console.print(f"[blue]Calling LLM ({config.model})...[/blue]")
    response = call_llm(messages, config)
    
    if response is None:
        return None
    
    # Parse response
    console.print("[dim]Parsing review...[/dim]")
    result = parse_review_response(response)
    
    if result:
        result.model_used = config.model
        result.raw_response = response
    
    return result
