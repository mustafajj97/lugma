"""Run a refresh without the web server — this is what the daily GitHub Action calls.

    python refresh.py                                  # all sources, local web/data files
    python refresh.py --sources news,instagram
    python refresh.py --prev-url https://your-site.netlify.app   # start from what's live (CI)

Exits with code 1 if Talabat (the main source) failed, so GitHub emails you.
"""
import argparse
import os
import sys
import time
import urllib.request

import engine

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


_last = [0]


def progress(done, total):
    if total and (done == total or done - _last[0] >= max(1, total // 10)):
        _last[0] = done
        log(f"  … {done}/{total}")
    if done < _last[0]:
        _last[0] = 0


def fetch_previous(site):
    """CI starts from a blank checkout: pull the live data so offers carry over between days."""
    for name in ("offers.json", "state.json"):
        url = f"{site.rstrip('/')}/data/{name}"
        try:
            body = urllib.request.urlopen(url, timeout=30).read()
            os.makedirs(engine.DATA_DIR, exist_ok=True)
            with open(os.path.join(engine.DATA_DIR, name), "wb") as f:
                f.write(body)
            log(f"Loaded previous {name} ({len(body) // 1024} KB) from {url}")
        except Exception as e:
            log(f"No previous {name} at {url} ({e}) — starting fresh")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="news,instagram,talabat")
    ap.add_argument("--prev-url", default=os.environ.get("SITE_URL", ""))
    a = ap.parse_args()
    if a.prev_url:
        fetch_previous(a.prev_url)
    wanted = [s for s in ("news", "instagram", "talabat") if s in a.sources.split(",")]
    failed = engine.run(wanted, log, progress)
    sys.exit(1 if "talabat" in failed else 0)
