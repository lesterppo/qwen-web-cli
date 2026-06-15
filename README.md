# qwen-web-cli v2

Browser-automation CLI + **native Hermes Agent tool** for Qwen Chat (chat.qwen.ai). No API key needed — uses your existing browser session.

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

# Multi-turn conversations (uses Qwen account-level memory)
python qwen.py -c chat.json "My name is Peter"
python qwen.py -c chat.json "What is my name?"

# Background execution with progress markers
python qwen.py --no-thinking -o out.md "prompt" 2>progress.log

# Pipe from stdin
echo "Hello" | python qwen.py
```

## Features

| Feature | Flag | Status |
|---------|------|--------|
| Text prompts | positional args, `-p`, or stdin | ✅ Works |
| JSON output | `--json` | ✅ Works |
| File output (agent-optimized) | `-o FILE` | ✅ Works |
| Multi-turn conversations | `-c FILE`, `--new` | ⚠️ Account memory only |
| Model selection | `-m qwen3-max` | ⚠️ UI-dependent |
| Image upload for analysis | `--image FILE` | ⚠️ Unreliable |
| Image generation extraction | `--extract-images DIR` | ❌ Not supported |
| Disable thinking | `--no-thinking` | ✅ Works (~16s vs ~25s) |
| Debug mode | `--debug` | ✅ Works |
| Persistent browser | `--persist` | ✅ Works |
| Progress markers | stderr: `[QWEN:LOADING/THINKING/DONE]` | ✅ Works |

## Capability Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Text prompts | ✅ WORKS | 16-25s latency |
| Multi-turn | ⚠️ PARTIAL | Qwen account memory works across sessions. chat_id deep-linking does NOT work |
| Model switching | ⚠️ PARTIAL | `-m qwen3-max/qwen3-coder` plumbed but Qwen UI selector not confirmed |
| Image upload | ⚠️ UNRELIABLE | Hidden input `#filesUpload` exists but `set_input_files()` doesn't trigger upload |
| Image generation | ❌ NOT SUPPORTED | Qwen 3.7 is text-only. Image gen requires Tongyi Wanxiang (separate product) |
| Token-efficient | ✅ WORKS | Returns ~50-char JSON pointer, full response on disk |
| Background exec | ✅ WORKS | Progress markers on stderr for `watch_patterns` |

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
# ~50 characters. Full response in result.md.
```

## Progress Markers

For background/async execution, progress markers are written to stderr:

```
[QWEN:LOADING]  — browser launching, page loading
[QWEN:THINKING] — Qwen is reasoning
[QWEN:DONE]     — response extracted and written to file
```

Use with `watch_patterns=["QWEN:DONE"]` for non-blocking polling.

## Hermes Agent Integration

This tool is also available as a **native Hermes Agent tool**. The tool registration lives at:

- `tools/qwen_tool.py` — tool schema, handler, check_fn
- `toolsets.py` — `"qwen"` added to `_HERMES_CORE_TOOLS`

The Hermes tool returns the same token-efficient JSON pointer. The agent uses `read_file` on the returned path to read the full response.

## Architecture

Alibaba's WAF (Web Application Firewall) + JS/WASM request signing makes direct HTTP impossible. Instead:

1. Launch headless Chromium via Playwright
2. Inject auth cookies
3. Navigate to chat.qwen.ai
4. Type the prompt into the chat textarea
5. Press Enter
6. Poll for "Thinking completed" → extract the final answer via JS DOM evaluation

## Known Limitations

- **~16-25s per query** (browser launch + page load + thinking time)
- **No streaming** — response is extracted after completion
- **No image generation** — Qwen 3.7 is text-only (Tongyi Wanxiang is separate)
- **Image upload unreliable** — upload button not found in authenticated DOM
- **Model switching partial** — Qwen UI may not expose clickable model selector
- Requires Playwright + Chromium

## License

MIT
