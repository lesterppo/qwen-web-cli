#!/usr/bin/env python3
"""Fast page server for Qwen — keeps chat page loaded, accepts queries via HTTP."""
import json, os, signal, sys, time, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock

QWEN_HOME = Path.home() / ".qwen-cli"
QWEN_AUTH = QWEN_HOME / "auth.json"
QWEN_URL = "https://chat.qwen.ai"
PORT = 9873
PID_FILE = QWEN_HOME / "server.pid"
_pg = _ctx = _pw = None
_lock = Lock()

def load_auth():
    if QWEN_AUTH.exists(): return json.loads(QWEN_AUTH.read_text())
    return {}

def init_browser():
    global _pw, _ctx, _pg
    from playwright.sync_api import sync_playwright
    auth = load_auth()
    profile_dir = str(QWEN_HOME / "browser-profile")
    _pw = sync_playwright().start()
    _ctx = _pw.chromium.launch_persistent_context(profile_dir, headless=True,
        viewport={"width": 1280, "height": 800},
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    # Qwen cookies
    for n, v in auth.get("cookies", {}).items():
        _ctx.add_cookies([{"name": n, "value": v, "domain": ".qwen.ai", "path": "/",
                           "httpOnly": False, "secure": True, "sameSite": "Lax"}])
    _pg = _ctx.pages[0] if _ctx.pages else _ctx.new_page()
    _pg.goto(QWEN_URL, timeout=30000)
    try: _pg.wait_for_selector("textarea", timeout=10000)
    except: time.sleep(3)
    print("Qwen server ready", flush=True)

def send_query(prompt: str) -> str:
    textbox = _pg.locator("textarea").first
    if not textbox.is_visible(timeout=5000):
        raise RuntimeError("Textarea not found")
    
    # Count existing "Thinking completed" blocks before sending
    pre_count = _pg.locator("body").inner_text().count("Thinking completed")
    old_body = _pg.locator("body").inner_text()
    textbox.fill(prompt); time.sleep(0.2)
    textbox.press("Enter")
    
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            body = _pg.locator("body").inner_text()
            
            # Wait for a NEW "Thinking completed" block (or body changed significantly)
            now_count = body.count("Thinking completed")
            body_grew = len(body) > len(old_body) + 20
            
            if now_count > pre_count or body_grew:
                time.sleep(1)  # Let final text render
                body = _pg.locator("body").inner_text()
                
                # Split on ALL "Thinking completed" — take the LAST one
                parts = body.split("Thinking completed")
                last = parts[-1]  # Most recent response
                
                lines = [l.strip() for l in last.split("\n") if l.strip()]
                result = [l for l in lines 
                          if l not in ("Auto", "Skip", "I prefer this response")
                          and not l.startswith("Qwen")
                          and "AI-generated" not in l
                          and "I prefer" not in l]
                if result:
                    return result[0]
                
                # Fallback: first substantial line after prompt
                after = body[body.rfind(prompt) + len(prompt):] if prompt in body else ""
                if after:
                    cand_lines = [l.strip() for l in after.split("\n") 
                                  if l.strip() and len(l) > 3 
                                  and l.strip() not in ("Auto", "Skip", "I prefer this response")
                                  and "AI-generated" not in l]
                    if cand_lines:
                        return cand_lines[0]
        except Exception:
            pass
        time.sleep(0.3)
    return ""

def cleanup():
    global _ctx, _pw
    if _ctx:
        try: _ctx.close()
        except: pass
    if _pw:
        try: _pw.stop()
        except: pass

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/query": self.send_error(404); return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try: prompt = json.loads(body).get("prompt", "")
        except: self.send_error(400); return
        with _lock:
            try: text = send_query(prompt)
            except Exception as e:
                self.send_response(500); self.send_header("Content-Type", "application/json")
                self.end_headers(); self.wfile.write(json.dumps({"ok": False, "err": str(e)}).encode()); return
        try:
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(json.dumps({"ok": True, "text": text}).encode())
        except BrokenPipeError:
            pass  # Client disconnected — normal for slow responses
    def do_GET(self):
        if self.path == "/health": self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        elif self.path == "/stop": self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); Thread(target=self.server.shutdown).start()
        else: self.send_error(404)
    def log_message(self, *a): pass

def run_server():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True); PID_FILE.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *a: (cleanup(), PID_FILE.unlink(missing_ok=True), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *a: (cleanup(), PID_FILE.unlink(missing_ok=True), sys.exit(0)))
    try: init_browser()
    except Exception as e: print(f"Init: {e}", file=sys.stderr); PID_FILE.unlink(missing_ok=True); sys.exit(1)
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Qwen server ready on :{PORT}", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); cleanup(); PID_FILE.unlink(missing_ok=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        if PID_FILE.exists():
            try: os.kill(int(PID_FILE.read_text().strip()), signal.SIGTERM); PID_FILE.unlink(missing_ok=True); print("Stopped")
            except: PID_FILE.unlink(missing_ok=True); print("Not running")
    elif len(sys.argv) > 1 and sys.argv[1] == "--status":
        if PID_FILE.exists():
            try: os.kill(int(PID_FILE.read_text().strip()), 0); print("Running")
            except: PID_FILE.unlink(missing_ok=True); print("Not running")
        else: print("Not running")
    else: run_server()
