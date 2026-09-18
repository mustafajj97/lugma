"""Lugma on your PC — the same app as the phone PWA, plus a Refresh button and Settings.

    python server.py          -> http://localhost:8760

Offers live in web/data/offers.json (written by engine.py) — the exact file the Netlify
site serves, so the PC and phone versions always look the same.
Pure standard library — nothing to install.
"""
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import engine
from collectors import talabat

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else int(os.environ.get("PORT", 8760))
STAGES = {"talabat": "Reading Talabat menus", "instagram": "Searching Instagram posts", "news": "Scanning Bahrain news"}
_lock = threading.Lock()
job = {"running": False, "source": None, "log": [], "done": 0, "total": 0, "stage": ""}


def log(msg):
    stamp = datetime.now().strftime("%H:%M:%S")
    try:
        print(f"[{stamp}] {msg}", flush=True)
    except Exception:  # a console problem must never abort a refresh
        pass
    with _lock:
        job["log"] = (job["log"] + [f"{stamp}  {msg}"])[-200:]
        for src, stage in STAGES.items():
            if msg.lower().startswith(src):
                job.update(source=src, stage=stage)


def progress(done, total):
    with _lock:
        job["done"], job["total"] = done, total


def run_refresh(sources):
    try:
        for src in sources:   # one at a time so the UI can show each source landing
            with _lock:
                job.update(source=src, stage=STAGES[src], done=0, total=0)
            engine.run([src], log, progress)
        log("Refresh finished")
    finally:
        with _lock:
            job.update(running=False, stage="")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(engine.ROOT, "web"), **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always pick up UI + data updates
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/status":
            with _lock:
                return self._json(dict(job))
        if u.path == "/api/settings":
            return self._json(engine.config())
        if u.path == "/api/areas":
            try:
                return self._json([x for x in talabat.areas() if "test" not in x["slug"]])
            except Exception as e:
                return self._json({"error": str(e)}, 502)
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/refresh":
            wanted = parse_qs(u.query).get("sources", ["talabat,instagram,news"])[0].split(",")
            wanted = [w for w in ("news", "instagram", "talabat") if w in wanted]  # quick sources first
            with _lock:
                if job["running"]:
                    return self._json({"error": "A refresh is already running"}, 409)
                job.update(running=True, log=[], done=0, total=0)
            threading.Thread(target=run_refresh, args=(wanted,), daemon=True).start()
            return self._json({"started": wanted})
        if u.path == "/api/settings":
            return self._json(engine.save_config(self._body()))
        return self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Lugma running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
