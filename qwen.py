#!/usr/bin/env python3
"""
CLI for Qwen Chat (chat.qwen.ai) via Playwright browser automation.

Qwen uses Alibaba WAF + JS/WASM request signing that blocks direct HTTP.
Instead, we launch headless Chromium, type into the chat UI, and extract
the response from the DOM. Auth via browser cookies (Firefox/Chrome/Edge).

Usage:
  python qwen.py -l                    # login via browser, capture cookies
  python qwen.py "Hello"               # text prompt
  python qwen.py -m qwen3-max "prompt" # model selection
  python qwen.py -c chat.json "msg"    # multi-turn conversation
  python qwen.py -o result.md "prompt" # write to file (agent-optimized)
  python qwen.py --json "prompt"       # JSON output
  echo "prompt" | python qwen.py       # stdin

Auth:
  - Login: python qwen.py -l (opens browser, saves cookies to ~/.qwen-cli/auth.json)
  - Manual: export QWEN_TOKEN=<jwt> QWEN_COOKIE_HEADER="token=...; lswusea=..."
"""

import os
import sys
import json
import time
import argparse
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

QWEN_HOME = Path.home() / ".qwen-cli"
QWEN_AUTH_FILE = QWEN_HOME / "auth.json"
QWEN_BROWSER_PROFILE = QWEN_HOME / "browser-profile"
QWEN_BASE_URL = "https://chat.qwen.ai"
QWEN_DEFAULT_MODEL = "qwen3.7-plus"

# ── helpers ──────────────────────────────────────────────

def fail(code: str, reason: str):
    print(json.dumps({"ok": False, "err": code, "msg": reason}, ensure_ascii=False))
    sys.exit(1)

def log(msg: str):
    if not sys.stdout.isatty():  # auto-quiet when piped
        return
    print(f"[qwen] {msg}", file=sys.stderr)

# ── auth ─────────────────────────────────────────────────

def read_auth():
    """Read saved auth from ~/.qwen-cli/auth.json"""
    if QWEN_AUTH_FILE.exists():
        try:
            return json.loads(QWEN_AUTH_FILE.read_text())
        except Exception:
            pass
    return None

def write_auth(data: dict):
    QWEN_HOME.mkdir(parents=True, exist_ok=True)
    QWEN_AUTH_FILE.write_text(json.dumps(data, indent=2))

def extract_cookies_from_browser():
    """Try to extract Qwen cookies from browser via browser_cookie3."""
    try:
        import browser_cookie3
        browsers = [
            ("chrome", browser_cookie3.chrome),
            ("firefox", browser_cookie3.firefox),
            ("edge", browser_cookie3.edge),
        ]
        for name, fetch_func in browsers:
            try:
                cj = fetch_func(domain_name=".qwen.ai")
                token = None
                lswusea = None
                cnaui = None
                for c in cj:
                    if c.name == "token":
                        token = c.value
                    elif c.name == "lswusea":
                        lswusea = c.value
                    elif c.name == "cnaui":
                        cnaui = c.value
                if token:
                    log(f"Cookies extracted from {name}")
                    return {"token": token, "lswusea": lswusea, "cnaui": cnaui}
            except Exception:
                continue
    except ImportError:
        pass

    # WSL fallback: read Firefox cookies.sqlite directly from Windows filesystem
    if sys.platform == "linux":
        result = _extract_firefox_wsl()
        if result and result.get("token"):
            return result

    return None


def _extract_firefox_wsl():
    """WSL: read Qwen cookies from Windows Firefox cookies.sqlite via SQLite."""
    import sqlite3
    import shutil

    # Find Firefox profile on Windows filesystem
    firefox_base = Path("/mnt/c/Users")
    profiles = []
    try:
        for user_dir in firefox_base.iterdir():
            if not user_dir.is_dir():
                continue
            ff_profiles = user_dir / "AppData/Roaming/Mozilla/Firefox/Profiles"
            if ff_profiles.exists():
                for p in ff_profiles.iterdir():
                    if p.is_dir() and (p / "cookies.sqlite").exists():
                        profiles.append(p / "cookies.sqlite")
    except PermissionError:
        pass

    for sqlite_path in profiles:
        try:
            tmp = Path("/tmp/qwen_cookies.sqlite")
            shutil.copy2(str(sqlite_path), str(tmp))
            conn = sqlite3.connect(str(tmp))
            cur = conn.cursor()
            cur.execute(
                "SELECT name, value FROM moz_cookies "
                "WHERE host LIKE '%qwen.ai%' AND (name='token' OR name='lswusea' OR name='cnaui')"
            )
            rows = cur.fetchall()
            conn.close()
            tmp.unlink(missing_ok=True)

            result = {}
            for name, value in rows:
                result[name] = value
            if result.get("token"):
                log(f"Cookies extracted from Firefox (WSL, {sqlite_path.parent.name})")
                return result
        except Exception:
            continue

    return None


def import_cookies_from_json(json_path: str):
    """Import cookies from a JSON file exported by a browser extension.

    The JSON file should be an array of cookie objects with 'name' and 'value'
    fields (e.g., exported by 'Cookie Editor' or 'EditThisCookie' extensions).
    """
    p = Path(json_path)
    if not p.exists():
        fail("no-file", f"File not found: {json_path}")

    try:
        cookies = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        fail("bad-json", f"Invalid JSON: {e}")

    if not isinstance(cookies, list):
        fail("bad-format", f"Expected array of cookies, got {type(cookies).__name__}")

    # Filter for qwen.ai cookies
    qwen_cookies = [
        c for c in cookies
        if isinstance(c, dict) and "qwen.ai" in str(c.get("domain", ""))
    ]

    if not qwen_cookies:
        fail("no-qwen-cookies", "No qwen.ai cookies found in file")

    # Extract required cookies
    token = None
    lswusea = None
    cnaui = None
    for c in qwen_cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name == "token":
            token = value
        elif name == "lswusea":
            lswusea = value
        elif name == "cnaui":
            cnaui = value

    if not token:
        fail("no-token", "No 'token' cookie found in qwen.ai cookies")

    # Validate JWT format
    if not re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', token):
        log("Warning: token doesn't look like a JWT (may still work)")

    cookie_parts = [f"token={token}"]
    if lswusea:
        cookie_parts.append(f"lswusea={lswusea}")
    if cnaui:
        cookie_parts.append(f"cnaui={cnaui}")

    auth_data = {
        "token": token,
        "cookie_header": "; ".join(cookie_parts),
        "lswusea": lswusea,
        "cnaui": cnaui,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    write_auth(auth_data)
    log(f"Imported cookies: token present, lswusea={'yes' if lswusea else 'no'}, cnaui={'yes' if cnaui else 'no'}")
    print(json.dumps({"ok": True, "msg": "Cookies imported and saved to ~/.qwen-cli/auth.json"}, ensure_ascii=False))

def browser_login():
    """Open visible browser for Qwen login, poll for cookies, save auth."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail("no-playwright", "pip install playwright && python -m playwright install chromium")

    log("Launching browser for Qwen login...")
    log("Log in at chat.qwen.ai, then close the browser window.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(QWEN_BROWSER_PROFILE),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded")

        log("Waiting for login (detecting JWT token cookie)...")
        timeout = 300  # 5 minutes
        for i in range(timeout):
            cookies = context.cookies()
            token_cookie = None
            lswusea_cookie = None
            cnaui_cookie = None
            for c in cookies:
                if c["name"] == "token":
                    token_cookie = c["value"]
                elif c["name"] == "lswusea":
                    lswusea_cookie = c["value"]
                elif c["name"] == "cnaui":
                    cnaui_cookie = c["value"]

            if token_cookie:
                # Build cookie header for later use
                cookie_parts = [f"token={token_cookie}"]
                if lswusea_cookie:
                    cookie_parts.append(f"lswusea={lswusea_cookie}")
                if cnaui_cookie:
                    cookie_parts.append(f"cnaui={cnaui_cookie}")

                auth_data = {
                    "token": token_cookie,
                    "cookie_header": "; ".join(cookie_parts),
                    "lswusea": lswusea_cookie,
                    "cnaui": cnaui_cookie,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
                write_auth(auth_data)
                log("Login successful! Auth saved to ~/.qwen-cli/auth.json")
                context.close()
                return auth_data

            if i % 30 == 0 and i > 0:
                elapsed = i
                log(f"Still waiting for login... ({elapsed}s)")

            time.sleep(1)

        context.close()
        fail("login-timeout", "Login not detected within 5 minutes.")


def get_auth():
    """Get auth from env vars, saved file, or browser cookies."""
    # Env vars (highest priority)
    token = os.environ.get("QWEN_TOKEN")
    cookie_header = os.environ.get("QWEN_COOKIE_HEADER")
    if token and cookie_header:
        return {"token": token, "cookie_header": cookie_header}

    if token:
        # Build minimal cookie header
        ch = f"token={token}"
        lsw = os.environ.get("QWEN_LSWUSEA")
        if lsw:
            ch += f"; lswusea={lsw}"
        return {"token": token, "cookie_header": ch}

    # Saved auth file
    auth = read_auth()
    if auth and auth.get("token") and auth.get("cookie_header"):
        return auth

    # Try browser cookie extraction
    browser_auth = extract_cookies_from_browser()
    if browser_auth and browser_auth.get("token"):
        cookie_parts = [f"token={browser_auth['token']}"]
        if browser_auth.get("lswusea"):
            cookie_parts.append(f"lswusea={browser_auth['lswusea']}")
        if browser_auth.get("cnaui"):
            cookie_parts.append(f"cnaui={browser_auth['cnaui']}")
        result = {
            "token": browser_auth["token"],
            "cookie_header": "; ".join(cookie_parts),
            "lswusea": browser_auth.get("lswusea"),
            "cnaui": browser_auth.get("cnaui"),
        }
        write_auth(result)
        return result

    fail("no-auth",
         "No Qwen auth found.\n"
         "Options:\n"
         "  1. python qwen.py -l              (browser login)\n"
         "  2. python qwen.py --import-cookies cookies.json  (import from extension)\n"
         "  3. export QWEN_TOKEN=<jwt> QWEN_COOKIE_HEADER='token=...; lswusea=...'\n"
         "WSL users: log into chat.qwen.ai in Windows Firefox first, then retry.\n"
         "Or export cookies from Chrome using 'Cookie Editor' extension and --import-cookies.")

# ── conversation state ───────────────────────────────────

def load_conversation(path: str) -> dict:
    """Load conversation file. Returns {chat_id, parent_id, history, model}."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}

def save_conversation(path: str, state: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── main CLI ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CLI for Qwen Chat (chat.qwen.ai) via browser cookie auth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          python qwen.py -l                          # Login via browser
          python qwen.py --import-cookies cookies.json  # Import from browser extension
          python qwen.py "Hello"                     # Text prompt
          python qwen.py -m qwen3-max "Complex task" # Model selection
          python qwen.py -c chat.json "Message"      # Multi-turn conversation
          python qwen.py --json "prompt"             # JSON output
          python qwen.py -o result.md "prompt"       # Write to file
          echo "prompt" | python qwen.py             # Stdin
        """),
    )

    parser.add_argument("prompt", nargs="*", help="Prompt text (or pipe via stdin)")
    parser.add_argument("-p", "--prompt-flag", help="Prompt via flag")
    parser.add_argument("-m", "--model", default=QWEN_DEFAULT_MODEL,
                        help=f"Model name (default: {QWEN_DEFAULT_MODEL})")
    parser.add_argument("-c", "--conversation", help="Conversation state file")
    parser.add_argument("--new", action="store_true", help="Start fresh conversation")
    parser.add_argument("-o", "--output", help="Write response to file")
    parser.add_argument("--json", action="store_true", help="JSON output on stdout")
    parser.add_argument("-l", "--login", action="store_true", help="Browser login flow")
    parser.add_argument("--import-cookies", metavar="FILE",
                        help="Import cookies from JSON file (browser extension export)")
    parser.add_argument("--brief", action="store_true", help="Concise mode")
    parser.add_argument("--no-thinking", action="store_true", help="Disable thinking")
    parser.add_argument("--no-search", action="store_true", help="Disable web search")
    parser.add_argument("--debug", action="store_true", help="Debug output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress stderr logs")

    args = parser.parse_args()

    # ── login mode ──
    if args.login:
        auth = browser_login()
        print(json.dumps({"ok": True, "msg": "Login saved to ~/.qwen-cli/auth.json"}, ensure_ascii=False))
        return

    # ── cookie import mode ──
    if args.import_cookies:
        import_cookies_from_json(args.import_cookies)
        return

    # ── resolve prompt ──
    prompt = None
    if args.prompt_flag:
        prompt = args.prompt_flag
    elif args.prompt:
        prompt = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()

    if not prompt:
        parser.print_help()
        print("\nError: No prompt provided. Use positional args, -p, or stdin.")
        sys.exit(1)

    # ── model ──
    model = args.model

    # ── conversation ──
    conv = {}
    chat_id = None
    if args.conversation:
        conv = load_conversation(args.conversation)
        if args.new:
            conv = {}
    chat_id = conv.get("chat_id")
    if conv.get("model"):
        model = conv["model"]  # use saved model from conversation

    # ── auth ──
    auth = get_auth()

    # ── send ──
    thinking = not args.no_thinking
    search = not args.no_search

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Use simple launch (not persistent) to avoid EPIPE driver bug
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
            )

            # Inject cookies
            cookies_to_set = []
            for cookie_str in auth["cookie_header"].split("; "):
                if "=" in cookie_str:
                    name, _, value = cookie_str.partition("=")
                    cookies_to_set.append({
                        "name": name, "value": value,
                        "domain": ".qwen.ai", "path": "/",
                        "httpOnly": name == "token", "secure": True, "sameSite": "Lax",
                    })
            context.add_cookies(cookies_to_set)

            page = context.new_page()

            # Navigate to existing chat or new
            if chat_id:
                page.goto(f"{QWEN_BASE_URL}/c/{chat_id}", wait_until="domcontentloaded", timeout=30000)
            else:
                page.goto(QWEN_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # Find and fill textbox
            textbox = page.locator("textarea").first
            if not textbox.is_visible(timeout=5000):
                fail("no-input", "Could not find chat input. Auth may have expired.")

            if args.debug:
                log(f"Sending prompt ({len(prompt)} chars)")

            textbox.fill(prompt)
            time.sleep(0.3)
            textbox.press("Enter")

            if args.debug:
                log("Waiting for response...")

            # Extract chat_id and wait for response
            response_text = ""
            deadline = time.time() + 180

            while time.time() < deadline:
                # Extract chat_id from URL once Qwen navigates to it
                if not chat_id:
                    m = re.search(r'/c/([a-f0-9-]{20,})', page.url)
                    if m:
                        chat_id = m.group(1)

                body = page.locator("body").inner_text()
                if prompt in body:
                    after_prompt = body[body.find(prompt) + len(prompt):]

                    # Wait for "Thinking completed" then extract final answer
                    if "Thinking completed" in after_prompt:
                        final = after_prompt.split("Thinking completed", 1)[1].strip()
                        # Take text until we hit UI chrome (Auto, Qwen, AI-generated, Skip)
                        lines = final.split("\n")
                        answer_lines = []
                        for line in lines:
                            s = line.strip()
                            if not s:
                                continue
                            if s in ("Auto", "Skip", "Qwen3.7-Plus") or \
                               s.startswith("Qwen") or s.startswith("AI-generated"):
                                continue
                            answer_lines.append(s)
                        answer = "\n".join(answer_lines).strip()
                        if answer and len(answer) > 1:
                            response_text = answer
                            break
                time.sleep(1)

            browser.close()

            if not response_text:
                fail("empty-response", "No response received. Auth may have expired.")

            # ── update conversation ──
            if args.conversation:
                conv["chat_id"] = chat_id
                conv["model"] = model
                save_conversation(args.conversation, conv)

            # ── output ──
            if args.output:
                out_path = Path(args.output)
                out_path.write_text(response_text, encoding="utf-8")
                size = out_path.stat().st_size
                code_blocks = response_text.count("```")
                result = {
                    "ok": True,
                    "f": str(out_path),
                    "s": size,
                    "b": code_blocks // 2,
                }
                if args.conversation:
                    result["c"] = chat_id
                print(json.dumps(result, ensure_ascii=False))
            elif args.json:
                print(json.dumps({
                    "ok": True,
                    "text": response_text,
                    "chat_id": chat_id,
                    "model": model,
                }, ensure_ascii=False))
            else:
                print(response_text)

    except SystemExit:
        raise
    except Exception as e:
        fail("error", str(e))


if __name__ == "__main__":
    main()
