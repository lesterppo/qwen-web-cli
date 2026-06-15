---
name: qwen-web-cli
description: CLI plus native Hermes tool for Qwen Chat via Playwright browser. Text-only model (Qwen3.7). 16-25s latency. Token-efficient JSON pointer output.
triggers:
  keywords:
    - Qwen
    - qwen
    - qwen-web-cli
    - chat.qwen.ai
  context:
    - User wants to use Qwen Chat from CLI
    - User needs free alternative model
    - User wants cross-model collaboration with Qwen
---

# qwen-web-cli v2

Browser-automation CLI for Qwen Chat (chat.qwen.ai). Uses headless Chromium via Playwright to type into the Qwen web UI and extract responses — Alibaba's WAF + request signing makes direct HTTP API calls impossible.

Script: `qwen.py`
Python: `python3`

## Quick Reference

```bash
# Agent-optimized output (15-token pointer, response on disk) — ALWAYS USE THIS
python qwen.py --no-thinking -o result.md "your prompt"

# JSON output — use when you need structured output
python qwen.py --no-thinking --json "your prompt"

# Multi-turn conversations (uses Qwen account-level memory)
python qwen.py -c chat.json "My name is Peter"
python qwen.py -c chat.json "What is my name?"

# Background execution with progress markers
python qwen.py --no-thinking -o out.md "prompt" 2>progress.log

# Pipe from stdin
echo "prompt" | python qwen.py
```

## Flags

| Flag | Purpose |
|------|---------|
| `-m MODEL` | Model name (qwen3.7-plus, qwen3-max, qwen3-coder) |
| `-c FILE` | Multi-turn conversation state file |
| `--new` | Start fresh with `-c` |
| `-o FILE` | Write response to file (agent-optimized, ~50-char stdout pointer) |
| `--json` | JSON output on stdout |
| `--no-thinking` | Disable thinking (saves ~10s) |
| `--no-search` | Disable web search |
| `--image FILE` | Image file to upload for analysis |
| `--extract-images DIR` | Save generated images to directory |
| `--persist` | Use persistent browser profile |
| `--debug` | Debug output |

## Capability Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Text prompts | ✅ WORKS | 16-25s latency |
| Multi-turn | ⚠️ PARTIAL | Qwen account memory works. chat_id deep-linking broken |
| Model switching | ⚠️ PARTIAL | Flag plumbed, UI selector not confirmed |
| Image upload | ⚠️ UNRELIABLE | #filesUpload hidden input exists, set_input_files fails |
| Image generation | ❌ NOT SUPPORTED | Qwen 3.7 is text-only. Tongyi Wanxiang is separate |
| Progress markers | ✅ WORKS | [QWEN:LOADING/THINKING/DONE] on stderr |

## Auth

**WSL (this environment):** Auto-extracts from Windows Firefox cookies via SQLite.
Log into https://chat.qwen.ai in Windows Firefox first. Cached at `~/.qwen-cli/auth.json`.

Other auth methods:
1. `python qwen.py -l` — opens visible browser for login
2. `python qwen.py --import-cookies cookies.json` — import from Chrome extension
3. `export QWEN_TOKEN=*** QWEN_COOKIE_HEADER='token=...; cnaui=...'` — manual env vars

## Architecture

Qwen Chat uses Alibaba WAF + JS/WASM request signing (`bx-ua` header) that blocks direct API calls. Browser automation is the only path:

1. Launch headless Chromium via Playwright
2. Inject auth cookies (token, cnaui, lswusea)
3. Navigate to chat.qwen.ai
4. Type prompt into textarea + press Enter
5. Poll for completion + extract response via JS DOM evaluation
6. Return clean text or JSON pointer

## Output Pointer Format (agent-optimized)

```json
{"ok": true, "f": "./result.md", "s": 450, "b": 2}
```

| Key | Meaning |
|-----|---------|
| `f` | File path |
| `s` | Response size in bytes |
| `b` | Number of code blocks |
| `c` | Chat ID (with `-c`) |
| `img` | Downloaded image paths (with `--extract-images`) |

## Known Limitations

- **16-25s latency** — browser launch + page load + inference
- **No streaming** — response extracted after completion
- **No image generation** — Qwen 3.7 is text-only
- **Image upload unreliable** — upload button not found in authenticated DOM
- **Model switching partial** — Qwen UI may not expose clickable selector
- **Auth expiry** — re-login in Firefox when `no-auth` error appears
- **Browser dependency** — Playwright + Chromium required
