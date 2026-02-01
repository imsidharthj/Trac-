"""HTML Report Renderer for Tracé.

Generates a single-file, self-contained HTML report that:
- Works offline
- Can be shared via Slack, JIRA, email
- Has a professional dashboard look

All CSS and JS are inlined for portability.
"""

import html
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader
from rich.console import Console

console = Console()


# ============================================================================
# HTML Template (Inlined for Single-File Output)
# ============================================================================

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tracé Review — {{ title }}</title>
    <style>
        /* Reset & Base */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --border-color: #30363d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-yellow: #d29922;
            --accent-blue: #58a6ff;
            --accent-purple: #a371f7;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }
        
        /* Layout */
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        /* Header */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 2rem;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .meta {
            text-align: right;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }
        
        /* Status Banner */
        .status-banner {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
        }
        
        .status-banner.pass {
            border-left: 4px solid var(--accent-green);
            background: linear-gradient(90deg, rgba(63, 185, 80, 0.1), transparent);
        }
        
        .status-banner.risk {
            border-left: 4px solid var(--accent-red);
            background: linear-gradient(90deg, rgba(248, 81, 73, 0.1), transparent);
        }
        
        .status-banner.missing {
            border-left: 4px solid var(--accent-yellow);
            background: linear-gradient(90deg, rgba(210, 153, 34, 0.1), transparent);
        }
        
        .status-icon {
            font-size: 3rem;
        }
        
        .status-content h1 {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }
        
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .status-badge.pass { background: var(--accent-green); color: #000; }
        .status-badge.risk { background: var(--accent-red); color: #fff; }
        .status-badge.missing { background: var(--accent-yellow); color: #000; }
        
        /* Section Cards */
        .section {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            margin-bottom: 1.5rem;
            overflow: hidden;
        }
        
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem 1.5rem;
            background: var(--bg-tertiary);
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
        }
        
        .section-header h2 {
            font-size: 1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .section-content {
            padding: 1.5rem;
        }
        
        /* Terminal Style (Evidence Locker) */
        .terminal {
            background: #0a0a0a;
            border-radius: 8px;
            overflow: hidden;
            font-family: 'SF Mono', 'Fira Code', 'Monaco', 'Consolas', monospace;
            font-size: 0.8125rem;
        }
        
        .terminal-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            background: #1a1a1a;
            border-bottom: 1px solid #333;
        }
        
        .terminal-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        
        .terminal-dot.red { background: #ff5f56; }
        .terminal-dot.yellow { background: #ffbd2e; }
        .terminal-dot.green { background: #27c93f; }
        
        .terminal-title {
            color: #888;
            margin-left: 0.5rem;
            font-size: 0.75rem;
        }
        
        .terminal-body {
            padding: 1rem;
            max-height: 400px;
            overflow-y: auto;
            color: #0f0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .terminal-body .error { color: #f85149; }
        .terminal-body .warning { color: #d29922; }
        .terminal-body .success { color: #3fb950; }
        
        /* Evidence Tabs */
        .evidence-tabs {
            display: flex;
            gap: 0.25rem;
            padding: 0 1rem;
            background: var(--bg-tertiary);
            border-bottom: 1px solid var(--border-color);
        }
        
        .evidence-tab {
            padding: 0.75rem 1rem;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.875rem;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        
        .evidence-tab:hover {
            color: var(--text-primary);
        }
        
        .evidence-tab.active {
            color: var(--accent-blue);
            border-bottom-color: var(--accent-blue);
        }
        
        .evidence-panel {
            display: none;
        }
        
        .evidence-panel.active {
            display: block;
        }
        
        /* Diff View */
        .diff-file {
            margin-bottom: 1.5rem;
        }
        
        .diff-file-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 1rem;
            background: var(--bg-tertiary);
            border-radius: 8px 8px 0 0;
            border: 1px solid var(--border-color);
            border-bottom: none;
        }
        
        .diff-filename {
            font-family: monospace;
            font-size: 0.875rem;
            color: var(--text-primary);
        }
        
        .diff-stats {
            font-size: 0.75rem;
        }
        
        .diff-stats .add { color: var(--accent-green); }
        .diff-stats .del { color: var(--accent-red); }
        
        .diff-content {
            background: #0d1117;
            border: 1px solid var(--border-color);
            border-radius: 0 0 8px 8px;
            font-family: monospace;
            font-size: 0.8125rem;
            overflow-x: auto;
        }
        
        .diff-line {
            display: flex;
            min-height: 1.5rem;
        }
        
        .diff-line-num {
            min-width: 50px;
            padding: 0 0.5rem;
            text-align: right;
            color: var(--text-muted);
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            user-select: none;
        }
        
        .diff-line-content {
            flex: 1;
            padding: 0 1rem;
            white-space: pre-wrap;
        }
        
        .diff-line.add {
            background: rgba(63, 185, 80, 0.15);
        }
        
        .diff-line.add .diff-line-content::before {
            content: '+';
            color: var(--accent-green);
            margin-right: 0.5rem;
        }
        
        .diff-line.del {
            background: rgba(248, 81, 73, 0.15);
        }
        
        .diff-line.del .diff-line-content::before {
            content: '-';
            color: var(--accent-red);
            margin-right: 0.5rem;
        }
        
        .diff-line.hunk {
            background: rgba(88, 166, 255, 0.1);
            color: var(--accent-blue);
        }
        
        /* Comments */
        .file-comments {
            margin-top: 0.75rem;
            padding: 1rem;
            background: var(--bg-tertiary);
            border-radius: 8px;
            border-left: 3px solid var(--accent-blue);
        }
        
        .comment {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        
        .comment:last-child {
            margin-bottom: 0;
        }
        
        .comment-icon {
            font-size: 1rem;
        }
        
        .comment-content {
            flex: 1;
        }
        
        .comment-line {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }
        
        .comment.critical .comment-icon { color: var(--accent-red); }
        .comment.high .comment-icon { color: #f97316; }
        .comment.warning .comment-icon { color: var(--accent-yellow); }
        .comment.info .comment-icon { color: var(--accent-blue); }
        
        /* Summary Text */
        .summary-text {
            font-size: 1rem;
            line-height: 1.7;
            color: var(--text-secondary);
        }
        
        /* Footer */
        .footer {
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.75rem;
        }
        
        .footer a {
            color: var(--accent-blue);
            text-decoration: none;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            .header {
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }
            
            .meta {
                text-align: left;
            }
        }
        
        /* Copy Button */
        .copy-btn {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.75rem;
        }
        
        .copy-btn:hover {
            background: var(--border-color);
            color: var(--text-primary);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="logo">Tracé</div>
            <div class="meta">
                <div>{{ timestamp }}</div>
                <div>Model: {{ model }}</div>
            </div>
        </header>
        
        <!-- Status Banner -->
        <div class="status-banner {{ status_class }}">
            <div class="status-icon">{{ status_icon }}</div>
            <div class="status-content">
                <h1>
                    <span class="status-badge {{ status_class }}">{{ status }}</span>
                </h1>
                <p class="summary-text">{{ summary }}</p>
            </div>
        </div>
        
        <!-- Evidence Analysis -->
        {% if evidence_analysis %}
        <section class="section">
            <div class="section-header">
                <h2>🔍 Evidence Analysis</h2>
            </div>
            <div class="section-content">
                <p class="summary-text">{{ evidence_analysis }}</p>
            </div>
        </section>
        {% endif %}
        
        <!-- Evidence Locker -->
        {% if evidence_sessions %}
        <section class="section">
            <div class="section-header">
                <h2>📦 Evidence Locker</h2>
            </div>
            
            {% if evidence_sessions|length > 1 %}
            <div class="evidence-tabs">
                {% for session in evidence_sessions %}
                <button class="evidence-tab {% if loop.first %}active{% endif %}" 
                        onclick="showEvidence('evidence-{{ loop.index }}', this)">
                    {{ session.command[:30] }}{% if session.command|length > 30 %}...{% endif %}
                </button>
                {% endfor %}
            </div>
            {% endif %}
            
            <div class="section-content">
                {% for session in evidence_sessions %}
                <div class="evidence-panel {% if loop.first %}active{% endif %}" id="evidence-{{ loop.index }}">
                    <div class="terminal">
                        <div class="terminal-header">
                            <span class="terminal-dot red"></span>
                            <span class="terminal-dot yellow"></span>
                            <span class="terminal-dot green"></span>
                            <span class="terminal-title">{{ session.command }}</span>
                            <button class="copy-btn" style="margin-left: auto;" 
                                    onclick="copyToClipboard('evidence-content-{{ loop.index }}')">
                                Copy
                            </button>
                        </div>
                        <div class="terminal-body" id="evidence-content-{{ loop.index }}">{{ session.output }}</div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted);">
                        Exit Code: 
                        {% if session.exit_code == 0 %}
                        <span style="color: var(--accent-green);">✓ {{ session.exit_code }}</span>
                        {% else %}
                        <span style="color: var(--accent-red);">✗ {{ session.exit_code }}</span>
                        {% endif %}
                        | Duration: {{ session.duration }}
                    </div>
                </div>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        
        <!-- Code Review -->
        {% if files %}
        <section class="section">
            <div class="section-header">
                <h2>📝 Code Review</h2>
            </div>
            <div class="section-content">
                {% for file in files %}
                <div class="diff-file">
                    <div class="diff-file-header">
                        <span class="diff-filename">{{ file.filename }}</span>
                        <span class="diff-stats">
                            {% if file.additions %}<span class="add">+{{ file.additions }}</span>{% endif %}
                            {% if file.deletions %}<span class="del">-{{ file.deletions }}</span>{% endif %}
                        </span>
                    </div>
                    
                    {% if file.diff_lines %}
                    <div class="diff-content">
                        {% for line in file.diff_lines %}
                        <div class="diff-line {{ line.type }}">
                            <span class="diff-line-num">{{ line.num or '' }}</span>
                            <span class="diff-line-content">{{ line.content }}</span>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                    
                    {% if file.comments %}
                    <div class="file-comments">
                        {% for comment in file.comments %}
                        <div class="comment {{ comment.severity }}">
                            <span class="comment-icon">
                                {% if comment.severity == 'critical' %}🔴
                                {% elif comment.severity == 'high' %}🟠
                                {% elif comment.severity == 'warning' %}🟡
                                {% else %}🔵{% endif %}
                            </span>
                            <div class="comment-content">
                                {% if comment.line %}
                                <div class="comment-line">Line {{ comment.line }}</div>
                                {% endif %}
                                <div>{{ comment.message }}</div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        
        <!-- Footer -->
        <footer class="footer">
            <p>Generated by <a href="#">Tracé</a> — Evidence-Based Code Reviews</p>
        </footer>
    </div>
    
    <script>
        function showEvidence(panelId, btn) {
            // Hide all panels
            document.querySelectorAll('.evidence-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.evidence-tab').forEach(t => t.classList.remove('active'));
            
            // Show selected
            document.getElementById(panelId).classList.add('active');
            btn.classList.add('active');
        }
        
        function copyToClipboard(elementId) {
            const text = document.getElementById(elementId).innerText;
            navigator.clipboard.writeText(text).then(() => {
                const btn = event.target;
                btn.innerText = 'Copied!';
                setTimeout(() => btn.innerText = 'Copy', 2000);
            });
        }
    </script>
</body>
</html>'''


# ============================================================================
# Helper Functions
# ============================================================================

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text) if text else ""


def colorize_terminal_output(text: str) -> str:
    """Add color classes to terminal output based on keywords."""
    lines = text.split("\n")
    result = []
    
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["error", "fail", "exception", "traceback", "fatal"]):
            result.append(f'<span class="error">{escape_html(line)}</span>')
        elif any(kw in line_lower for kw in ["warning", "warn", "deprecated"]):
            result.append(f'<span class="warning">{escape_html(line)}</span>')
        elif any(kw in line_lower for kw in ["pass", "success", "ok", "✓"]):
            result.append(f'<span class="success">{escape_html(line)}</span>')
        else:
            result.append(escape_html(line))
    
    return "\n".join(result)


def parse_diff_lines(diff_content: str) -> list[dict[str, Any]]:
    """Parse diff content into structured lines."""
    lines = []
    line_num = 0
    
    for line in diff_content.split("\n"):
        if line.startswith("@@"):
            # Hunk header
            lines.append({"type": "hunk", "num": None, "content": escape_html(line)})
            # Extract line number from hunk header
            match = re.search(r"\+(\d+)", line)
            if match:
                line_num = int(match.group(1)) - 1
        elif line.startswith("+") and not line.startswith("+++"):
            line_num += 1
            lines.append({"type": "add", "num": line_num, "content": escape_html(line[1:])})
        elif line.startswith("-") and not line.startswith("---"):
            lines.append({"type": "del", "num": "", "content": escape_html(line[1:])})
        else:
            if not line.startswith("---") and not line.startswith("+++"):
                line_num += 1
                lines.append({"type": "", "num": line_num, "content": escape_html(line)})
    
    return lines


def get_status_info(status: str) -> tuple[str, str, str]:
    """Get status class, icon, and display text."""
    status_upper = status.upper().replace("_", " ")
    
    if status_upper == "PASS":
        return "pass", "✅", "PASS"
    elif "RISK" in status_upper:
        return "risk", "⚠️", "RISK DETECTED"
    elif "MISSING" in status_upper:
        return "missing", "❓", "MISSING EVIDENCE"
    else:
        return "risk", "❌", status_upper


# ============================================================================
# Main Render Function
# ============================================================================

def render_review_html(
    review_result: dict[str, Any],
    evidence_sessions: list[dict[str, Any]] | None = None,
    diff_files: list[dict[str, Any]] | None = None,
    model: str = "Unknown",
) -> str:
    """Render a review result to HTML.
    
    Args:
        review_result: The review result dictionary.
        evidence_sessions: List of evidence session data.
        diff_files: List of diff file data.
        model: The model used for the review.
    
    Returns:
        Rendered HTML string.
    """
    # Get status info
    status = review_result.get("status", "unknown")
    status_class, status_icon, status_display = get_status_info(status)
    
    # Prepare evidence sessions
    formatted_evidence = []
    if evidence_sessions:
        for session in evidence_sessions:
            stdout = session.get("stdout", "")
            stderr = session.get("stderr", "")
            output = stdout + ("\n" + stderr if stderr else "")
            
            formatted_evidence.append({
                "command": session.get("command", "Unknown command"),
                "output": colorize_terminal_output(output),
                "exit_code": session.get("exit_code", "?"),
                "duration": f"{session.get('duration_ms', 0)}ms",
            })
    
    # Prepare files with diff and comments
    formatted_files = []
    review_files = review_result.get("files", [])
    
    if diff_files:
        for diff_file in diff_files:
            filename = diff_file.get("filename", "")
            
            # Find matching review comments
            comments = []
            for rf in review_files:
                if rf.get("filename") == filename:
                    comments = rf.get("comments", [])
                    break
            
            formatted_files.append({
                "filename": filename,
                "additions": diff_file.get("additions", 0),
                "deletions": diff_file.get("deletions", 0),
                "diff_lines": parse_diff_lines(diff_file.get("diff_content", "")),
                "comments": comments,
            })
    elif review_files:
        # No diff data, just show comments
        for rf in review_files:
            formatted_files.append({
                "filename": rf.get("filename", "unknown"),
                "additions": 0,
                "deletions": 0,
                "diff_lines": [],
                "comments": rf.get("comments", []),
            })
    
    # Create Jinja2 environment
    env = Environment(loader=BaseLoader(), autoescape=False)
    template = env.from_string(HTML_TEMPLATE)
    
    # Render
    html_output = template.render(
        title=review_result.get("summary", "Code Review")[:50],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        model=model,
        status=status_display,
        status_class=status_class,
        status_icon=status_icon,
        summary=escape_html(review_result.get("summary", "")),
        evidence_analysis=escape_html(review_result.get("evidence_analysis", "")),
        evidence_sessions=formatted_evidence,
        files=formatted_files,
    )
    
    return html_output


# ============================================================================
# File Operations
# ============================================================================

def get_traces_directory(base_path: Path | None = None) -> Path:
    """Get the traces directory, creating it if necessary."""
    from ..core.storage import get_ai_directory, initialize_storage
    
    initialize_storage(base_path)
    ai_dir = get_ai_directory(base_path)
    traces_dir = ai_dir / "traces"
    traces_dir.mkdir(exist_ok=True)
    return traces_dir


def save_trace(
    html_content: str,
    filename: str | None = None,
    base_path: Path | None = None,
) -> Path:
    """Save an HTML trace to the traces directory.
    
    Args:
        html_content: The HTML content to save.
        filename: Optional filename. Auto-generated if None.
        base_path: Base directory for .ai/ storage.
    
    Returns:
        Path to the saved file.
    """
    traces_dir = get_traces_directory(base_path)
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trace_{timestamp}.html"
    
    file_path = traces_dir / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return file_path


def open_in_browser(file_path: Path) -> bool:
    """Open a file in the default web browser.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        webbrowser.open(f"file://{file_path.absolute()}")
        return True
    except Exception as e:
        console.print(f"[yellow]Warning: Could not open browser: {e}[/yellow]")
        return False
