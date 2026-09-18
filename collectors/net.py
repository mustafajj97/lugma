import gzip
import threading
import time
import urllib.request
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# Per-host pacing: minimum seconds between requests to the same host, shared by all threads.
# Talabat answers 429 if hit much faster than ~3 requests/second.
RATE = {"www.talabat.com": 0.22}
_next_slot, _slot_lock = {}, threading.Lock()


def _wait_turn(host):
    gap = RATE.get(host)
    if not gap:
        return
    with _slot_lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0))
        _next_slot[host] = slot + gap
    if slot > now:
        time.sleep(slot - now)


def _cool_down(host, seconds):
    """After a 429, push everyone's next slot for that host back."""
    with _slot_lock:
        _next_slot[host] = max(_next_slot.get(host, 0), time.monotonic() + seconds)


def get(url, timeout=25, retries=3, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"}
    h.update(headers or {})
    host = urlparse(url).hostname
    last = None
    for attempt in range(retries + 1):
        _wait_turn(host)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except Exception as e:  # network blips are common on long runs; back off and retry
            last = e
            code = getattr(e, "code", None)
            if code in (403, 404):
                break
            if code == 429:
                ra = e.headers.get("Retry-After") if getattr(e, "headers", None) else None
                wait = int(ra) if ra and ra.isdigit() else 15 * (attempt + 1)
                _cool_down(host, wait)
            else:
                time.sleep(1.5 * (attempt + 1))
    raise last
