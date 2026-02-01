# Tracé (The AI Witness) 🕵️‍♂️

**Evidence-backed code reviews. Zero hallucinations.**

Tracé is an AI code reviewer that doesn't just read your code—it witnesses it working. Unlike standard bots that guess if code is correct, **Tracé captures real evidence** (like passing test logs) and combines it with your AI conversation history to generate a **Proof-of-Work** review you can trust.

> *"Don't just say you tested it. Prove it."*

## 🎬 Demo Video

[![Watch Demo Video](https://img.shields.io/badge/▶️_Watch_Demo-Google_Drive-blue)](https://drive.google.com/file/d/1BTaBhK1iAAzUaaKkIfL0z3RY1QcEPWCu/view?usp=sharing)

---

## ⚡ Why Tracé?

| Feature | Standard AI Bots | Tracé (The Witness) |
|---------|------------------|---------------------|
| **Context** | Only sees the code diff. | Sees tests, build logs, and your reasoning. |
| **Trust** | *"I think this looks okay."* | *"Tests passed at 10:42 AM. (See logs)."* |
| **Privacy** | Uploads code to 3rd party servers. | **Local-first.** Runs on your machine. Redacts secrets. |
| **Artifact** | A comment in GitHub. | A shareable, interactive **HTML Dashboard**. |

---

## 🔍 How It Works

1. **Captures Evidence** — Runs your local commands (`pytest`, `npm test`) and records the actual output as proof.

2. **Learns Intent** — Reads your recent chat history with AI assistants (Gemini, Claude, Antigravity) to understand *why* you made the changes.

3. **Analyzes Code** — Parses your Git diff to see exactly what files changed.

4. **Generates the Trace** — Combines **Code + Intent + Evidence** into a single, shareable HTML dashboard that proves your PR is ready to merge.

---

## 🚀 Quick Start

### Clone & Install

```bash
# Clone the repository
git clone git@github.com:imsidharthj/Trac-.git
cd Trac-

# Install with uv (recommended)
uv tool install .

# Or via pip
pip install -e .
```

---

## 🤖 MCP Setup (For AI Agents)

Tracé can run as an MCP (Model Context Protocol) server, allowing AI agents like **Codex**, **Claude Desktop**, or **Cursor** to use its capabilities directly.

### Step 1: Add to Codex Configuration

Add the following to your `~/.codex/config.toml`:

```toml
[mcp_servers.trace]
command = "/home/YOUR_USER/.local/bin/trace"  # Adjust path to your trace binary
args = ["serve"]
startup_timeout_sec = 200

[mcp_servers.trace.env]
OPENAI_API_KEY = "sk-..."  # Or use GEMINI_API_KEY, ANTHROPIC_API_KEY
```

### Step 2: Configure the Model

```bash
trace config set --model gpt-4o-mini
```

> **Tip:** Find your trace binary path with `which trace`

### Step 3: Use Tracé Tools in Your Agent

Once configured, you can use these tools in your AI agent:

```
# Capture evidence from a command
Use trace.run_and_capture with command "pytest -v" and cwd "/path/to/project"

# List recent evidence sessions
Use trace.get_recent_evidence to list the last 5 captured sessions

# Ingest Antigravity conversation context
Use trace.ingest_context with source "antigravity"

# Get git diff as structured JSON
Use trace.get_diff to get the current changes

# Generate a full AI-powered review
Use trace.full_review with open_browser false

# Generate a basic HTML report (without LLM analysis)
Use trace.generate_report with open_browser false

# Test LLM connectivity
Use trace.test_llm with prompt "Summarize what a code review does in 10 words."
```

### Available MCP Tools

| Tool | Purpose |
|------|---------|
| `trace.run_and_capture` | Execute a command and capture output as evidence |
| `trace.get_recent_evidence` | List recently captured evidence sessions |
| `trace.ingest_context` | Load AI conversation context (Antigravity, Gemini, Claude) |
| `trace.get_diff` | Get current git diff as structured JSON |
| `trace.analyze_code` | Run LLM analysis on current changes |
| `trace.full_review` | Complete review pipeline with HTML report |
| `trace.generate_report` | Generate HTML report from captured evidence |

---

## 💡 CLI Usage Workflow

### 1. Capture Evidence

Don't change your workflow. Just wrap your commands with `trace run`. This captures the output, exit code, and timestamp.

```bash
# Run your tests and let Tracé watch
trace run pytest tests/test_auth.py

# Or import an existing log file
npm test > build.log
trace capture --log build.log
```

View captured evidence:

```bash
trace list
```

### 2. Ingest Context

Did you use an AI CLI (Gemini/Claude) to write the code? Don't lose that context.

```bash
# Ingest conversation from Gemini CLI
trace context add --source gemini

# Or add a specific conversation file
trace context add --source gemini --file conversation.json
```

> **Note:** All context is auto-redacted for API keys and secrets before storage.

View ingested context:

```bash
trace context list
trace context show <session-id>
```

### 3. Generate Review

Generate the evidence-backed review.

```bash
# Review changes and open the dashboard
trace review --open

# Or save to a custom path
trace review --output ./my-review.html

# Get raw JSON output
trace review --json
```

**Output:** A beautiful `review.html` dashboard containing:

- ✅ **Status Banner** (PASS / RISK / MISSING)
- 📜 **Evidence Locker** (Your actual test logs)
- 📝 **Code Review** (Diffs with AI annotations)

---

## 📋 Command Reference

```bash
# Evidence Capture
trace run <command>           # Execute and record a command
trace capture --log <file>    # Import existing log file
trace list                    # List evidence sessions

# Context Ingestion
trace context add --source gemini         # Paste or import context
trace context add --source claude         # Claude context
trace context add --file <path>           # Import from file
trace context list                        # List context sessions
trace context show <id>                   # Display session

# Configuration
trace config set --model <model>          # Set LLM model
trace config show                         # Show current config

# Review Generation
trace review                  # Generate review + HTML
trace review --open           # Open in browser
trace review --staged         # Review staged changes only
trace review --json           # Output raw JSON

# MCP Server
trace serve                   # Start MCP server on STDIO
```

---

## 🔒 Privacy & Security

- **Redaction Layer:** Tracé scans all logs and context for sensitive patterns (API keys, PEM files, JWTs) before they leave your machine.

- **Local Storage:** All evidence is stored in the hidden `.ai/` directory in your repo.

- **Opt-In:** Tracé never reads your shell history or AI logs without an explicit command.

**Detected & Redacted Patterns:**
- OpenAI API Keys (`sk-...`, `sk-proj-...`)
- Anthropic API Keys (`sk-ant-...`)
- Google API Keys (`AIza...`)
- AWS Access Keys (`AKIA...`)
- GitHub Tokens (`ghp_...`, `gho_...`)
- Private Keys (PEM format)
- Bearer Tokens
- JWTs
- Passwords in URLs

---

## 📁 Project Structure

```
.ai/                          # Local storage (gitignore this)
├── evidence/                 # Captured command outputs
├── context/                  # Ingested AI conversations
├── traces/                   # Generated HTML reports
└── config.json               # User configuration

src/trace_cli/
├── cli.py                    # Main CLI entry point
├── mcp_server.py             # MCP protocol server
├── core/
│   ├── capture.py            # Real-time command capture
│   ├── storage.py            # Local storage management
│   ├── redaction.py          # Security: secret detection
│   ├── config.py             # Configuration management
│   ├── git_context.py        # Git diff analysis
│   ├── analyzer.py           # LLM-powered review engine
│   └── adapters/             # Context source adapters
└── output/
    └── renderer.py           # HTML report generator
```

---

## 🤝 Contributing

Tracé is a tool for developers, by developers.

| Module | Location | Purpose |
|--------|----------|---------|
| Capture | `src/trace_cli/core/capture.py` | Real-time command execution |
| Review Brain | `src/trace_cli/core/analyzer.py` | LLM orchestration |
| Renderer | `src/trace_cli/output/renderer.py` | HTML dashboard |
| Redaction | `src/trace_cli/core/redaction.py` | Secret detection |
| MCP Server | `src/trace_cli/mcp_server.py` | Agent integration |

---

## 📄 License

Apache 2.0

---

Built with ❤️ using [Typer](https://typer.tiangolo.com/), [Rich](https://rich.readthedocs.io/), and [LiteLLM](https://github.com/BerriAI/litellm).
