# qwen-web-cli

Browser-automation CLI for **Qwen Chat** (chat.qwen.ai). No API key needed — uses your existing browser session.

Qwen Chat uses Alibaba WAF + JS/WASM request signing that blocks all direct HTTP API calls. Instead, we launch headless Chromium, type into the Qwen web UI, and extract the response from the DOM.

## Install

```bash
pip install playwright
python -m playwright install chromium
```

## Quick Start

Log into [chat.qwen.ai](https://chat.qwen.ai) in your browser first.

```bash
# Text prompt
python qwen.py "Explain quantum computing in 3 bullet points"

# JSON output
python qwen.py --json "What is 2+2?"

# Agent-optimized output (tiny pointer on stdout, full response on disk)
python qwen.py -o result.md "Write a haiku about code"

# Multi-turn conversations
python qwen.py -c chat.json "My name is Peter"
python qwen.py -c chat.json "What is my name?"

# Pipe from stdin
echo "Hello" | python qwen.py
```

## Features

| Feature | Flag |
|---|---|
| Text prompts | positional args, `-p`, or stdin |
| JSON output | `--json` |
| File output (agent-optimized) | `-o FILE` |
| Multi-turn conversations | `-c FILE`, `--new` |
| Model selection | `-m qwen3-max` |
| Disable thinking | `--no-thinking` |
| Debug mode | `--debug` |

## Auth

The CLI auto-detects your Qwen session from browser cookies (Firefox, Chrome, Edge).

**Additional methods:**
- `python qwen.py -l` — opens browser for interactive login
- `python qwen.py --import-cookies cookies.json` — import from browser extension
- `export QWEN_TOKEN=<jwt> QWEN_COOKIE_HEADER='...'` — manual env vars

### WSL (Windows Subsystem for Linux)

Log into [chat.qwen.ai](https://chat.qwen.ai) in **Windows Firefox**. The CLI reads cookies directly from the Firefox SQLite database on the Windows filesystem. No config needed.

## Agent-Optimized Output

For AI agent consumption, use `-o` to write responses to disk. The CLI returns only a tiny pointer:

```bash
python qwen.py -o result.md "Write a haiku about code"

# stdout: {"ok": true, "f": "./result.md", "s": 55, "b": 0}
# ~15 tokens. Full response in result.md.
```

## Architecture

Alibaba's WAF (Web Application Firewall) + JS/WASM request signing makes direct HTTP impossible. Instead:

1. Launch headless Chromium via Playwright
2. Inject auth cookies
3. Navigate to chat.qwen.ai
4. Type the prompt into the chat textarea
5. Press Enter
6. Poll for "Thinking completed" → extract the final answer

## Limitations

- **~30s per query** (browser launch + page load + thinking time)
- **No streaming** — response is extracted after completion
- Requires Playwright + Chromium

## License

MIT
