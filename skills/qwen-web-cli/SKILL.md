---
name: qwen-web-cli
description: CLI for Qwen Chat (chat.qwen.ai) via Playwright browser automation. Auth via browser cookies, uses headless Chromium to interact with the chat UI (Alibaba WAF blocks direct API calls).
triggers:
  keywords:
    - Qwen
    - qwen
    - qwen-web-cli
    - chat.qwen.ai
  context:
    - User wants to use Qwen Chat from CLI
    - User needs browser-cookie auth for Qwen
    - User wants Qwen for reasoning/coding tasks
---

# qwen-web-cli

Browser-automation CLI for Qwen Chat (chat.qwen.ai). Uses headless Chromium via Playwright to type into the Qwen web UI and extract responses — Alibaba's WAF + request signing makes direct HTTP API calls impossible.

Script: `/home/peter/.hermes/scripts/qwen/qwen.py`
Python: `/home/peter/.hermes/hermes-agent/.venv/bin/python3`

## Quick Reference

```bash
QWEN=/home/peter/.hermes/scripts/qwen/qwen.py
PY=/home/peter/.hermes/hermes-agent/.venv/bin/python3

# Text prompt
$PY $QWEN "Explain quantum computing in 3 bullet points"

# JSON output
$PY $QWEN --json "What is 2+2?"

# Agent-optimized output (15-token pointer, response on disk)
$PY $QWEN -o result.md "Write a haiku about code"

# Multi-turn conversations
$PY $QWEN -c chat.json "My name is Peter"
$PY $QWEN -c chat.json "What is my name?"

# Start fresh conversation
$PY $QWEN -c chat.json --new "New topic"

# Stdin
echo "Hello" | $PY $QWEN

# Login via browser
$PY $QWEN -l

# Import cookies from browser extension JSON export
$PY $QWEN --import-cookies cookies.json
```

## Flags

| Flag | Purpose |
|------|---------|
| `-m MODEL` | Model name (default: qwen3.7-plus) |
| `-c FILE` | Multi-turn conversation state file |
| `--new` | Start fresh with `-c` |
| `-o FILE` | Write response to file (agent-optimized) |
| `--json` | JSON output on stdout |
| `-l` / `--login` | Browser login flow |
| `--import-cookies FILE` | Import cookies from JSON export |
| `--no-thinking` | Disable thinking mode |
| `--no-search` | Disable web search |
| `--debug` | Debug output |

## Auth

**WSL (this environment):** Auto-extracts cookies from Windows Firefox cookies.sqlite.
Just log into https://chat.qwen.ai in Firefox first, then the CLI finds your session.

Other auth methods:
1. `python qwen.py -l` — opens visible browser for login
2. `python qwen.py --import-cookies cookies.json` — import from Chrome extension export
3. `export QWEN_TOKEN=<jwt> QWEN_COOKIE_HEADER='token=...; cnaui=...'` — manual env vars

Cookies are cached at `~/.qwen-cli/auth.json` after first extraction.

## Architecture

Qwen Chat uses Alibaba WAF (Web Application Firewall) + JS/WASM-based request signing (`bx-ua` header). Direct HTTP requests — even with valid cookies — are blocked with a challenge page.

Instead of reverse-engineering the signing, we use browser automation:
1. Launch headless Chromium via Playwright
2. Inject auth cookies
3. Navigate to chat.qwen.ai
4. Type the prompt into the chat textarea
5. Press Enter
6. Poll body text for "Thinking completed" then extract the final answer
7. Return clean response text

## Output Pointer Format (agent-optimized)

```json
{"ok": true, "f": "./result.md", "s": 450, "b": 2}
```

| Key | Meaning |
|-----|---------|
| `f` | File path (relative when under cwd) |
| `s` | Response size in bytes |
| `b` | Number of code blocks |
| `c` | Chat ID (with `-c`) |

## Known Limitations

- **~30s latency:** Headless Chromium launch + page load + thinking time = ~30s per query
- **Thinking mode:** Qwen shows reasoning first. We wait for "Thinking completed" before extracting the answer. Use `--no-thinking` for faster responses.
- **No streaming:** Response is extracted after completion, not streamed in real-time
- **Browser dependency:** Requires Playwright (pip install playwright) + Chromium (python -m playwright install chromium)

## Dependencies

- `playwright` — browser automation
- `browser_cookie3` — cookie extraction (optional, WSL uses SQLite fallback)
