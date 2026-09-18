"""The refresh engine shared by the local app (server.py) and the daily cloud job (refresh.py).

Reads config.json, runs the collectors, stamps every offer with `validUntil`, drops anything
expired, and writes the files the web app reads:

    web/data/offers.json   everything the app shows (published)
    web/data/state.json    bookkeeping between runs: first-seen dates, Instagram query rotation
"""
import json
import os
import traceback
from datetime import date, datetime, timedelta, timezone

from collectors import cuisine, freshness, instagram, news, talabat

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "web", "data")
CONFIG = os.path.join(ROOT, "config.json")
BAHRAIN = timezone(timedelta(hours=3))

DEFAULT_CONFIG = {
    # Seef, Muharraq, East Riffa — north/centre/south. The first area gets a full sweep (~7 min),
    # each extra one a quick pass (~2 min); offer restaurants overlap heavily between areas.
    "areas": ["1006", "997", "1115"],
    "igAccounts": [],          # restaurant handles always searched, e.g. "papajohnsbahrain"
    "igQueries": [],           # extra search phrases, e.g. "bahrain karak offer"
    "igDefaultDays": 7,        # Instagram offer with no stated end date: shown for 7 days after posting
    "newsDefaultDays": 10,     # same for press stories
    "recurringDays": 30,       # "every Monday" style deals
    "talabatGraceDays": 1,     # Talabat offer stays visible 1 day after the last refresh confirmed it
}


def today():
    return datetime.now(BAHRAIN).date()


def now_iso():
    return datetime.now(BAHRAIN).isoformat(timespec="seconds")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def config():
    c = dict(DEFAULT_CONFIG)
    c.update(load_json(CONFIG, {}))
    return c


def save_config(updates):
    c = config()
    c.update({k: v for k, v in updates.items() if k in DEFAULT_CONFIG})
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    return c


def _slim(o):
    """Keep the published file small enough for phones."""
    for i in o.get("items", []):
        i.pop("img", None)
        if i.get("desc"):
            i["desc"] = i["desc"][:100]
    return o


def normalize(o):
    """Re-apply the current classification rules to an offer, so rule changes reach the live
    data straight away instead of waiting for the next full refresh."""
    if o["source"] == "talabat":
        raw = o.get("rawCuisines") or []
        o["cuisines"] = cuisine.classify(raw, o["restaurant"])
        o["primary"] = cuisine.primary(raw, o["restaurant"])
        for i in o.get("items", []):
            i["cuisines"] = cuisine.classify(text=i["name"])
    elif o["source"] == "news" and "news.google.com" in (o.get("url") or ""):
        o["url"] = news.resolve_google_news(o["url"]) or o["url"]
    return o


def _stamp(o, source, cfg, t):
    """Give a freshly collected offer its validity window."""
    o["checkedAt"] = now_iso()
    if source == "talabat":
        o["validUntil"] = (t + timedelta(days=cfg["talabatGraceDays"])).isoformat()
        o["validHow"] = "checked"
        return o
    posted = date.fromisoformat(o["date"]) if o.get("date") else date.fromisoformat(o.get("firstSeen") or t.isoformat())
    text = f"{o.get('title', '')} {o.get('detail', '')}"
    days = cfg["igDefaultDays"] if source == "instagram" else cfg["newsDefaultDays"]
    until, how = freshness.valid_until(text, posted, days, cfg["recurringDays"])
    o["validUntil"], o["validHow"] = until.isoformat(), how
    return o


def _live(o, t):
    return (o.get("validUntil") or "0000") >= t.isoformat()


class Store:
    def __init__(self, data_dir=DATA_DIR):
        self.dir = data_dir
        self.offers_path = os.path.join(data_dir, "offers.json")
        self.state_path = os.path.join(data_dir, "state.json")
        self.db = load_json(self.offers_path, {"offers": [], "sources": {}})
        self.state = load_json(self.state_path, {"seen": {}, "igNext": 0})

    def by_source(self, source):
        return [o for o in self.db["offers"] if o["source"] == source]

    def put(self, source, offers, ok=True, note=""):
        """Replace one source's offers. Always drops anything expired, from every source."""
        t = today()
        seen = self.state.setdefault("seen", {})
        for o in offers:
            o["firstSeen"] = seen.setdefault(o["id"], t.isoformat())
        others = [o for o in self.db["offers"] if o["source"] != source]
        self.db["offers"] = [o for o in others + [_slim(normalize(o)) for o in offers] if _live(o, t)]
        live_ids = {o["id"] for o in self.db["offers"]}
        # forget first-seen dates of offers gone for a month (keeps state.json small)
        cutoff = (t - timedelta(days=30)).isoformat()
        self.state["seen"] = {k: v for k, v in seen.items() if k in live_ids or v >= cutoff}
        self.db["sources"][source] = {
            "updatedAt": now_iso(), "ok": ok, "note": note,
            "count": sum(1 for o in self.db["offers"] if o["source"] == source),
        }
        self.save()

    def normalize_all(self):
        t = today()
        self.db["offers"] = [normalize(o) for o in self.db["offers"] if _live(o, t)]

    def save(self, touch=True):
        """touch=False keeps "Updated …" at the last real collection (e.g. when only republishing)."""
        if touch or not self.db.get("generatedAt"):
            self.db["generatedAt"] = now_iso()
        self.db["cuisines"] = cuisine.ORDER
        save_json(self.offers_path, self.db)
        save_json(self.state_path, self.state)


def run(sources, log, progress, store=None):
    """Refresh the given sources. Returns the list of sources that failed."""
    store = store or Store()
    cfg = config()
    t = today()
    failed = []
    for src in sources:
        try:
            if src == "talabat":
                prev = {o["id"]: o for o in store.by_source("talabat") if _live(o, t)}
                all_areas = {a["id"]: a for a in talabat.areas()}
                chosen = [all_areas[i] for i in cfg["areas"] if i in all_areas]

                def partial(got):
                    fresh = {o["id"] for o in got}
                    store.put("talabat", [o for i, o in prev.items() if i not in fresh] +
                              [_stamp(o, "talabat", cfg, t) for o in got if "checkedAt" not in o])

                offers = talabat.collect(chosen, log, progress, previous=prev, partial=partial)
                # menus that failed were filled from the last run: they keep their old validUntil
                store.put("talabat", [o if o.get("id") in prev and o is prev[o["id"]] else _stamp(o, "talabat", cfg, t)
                                      for o in offers])

            elif src == "instagram":
                found, store.state["igNext"], blocked = instagram.collect(
                    cfg["igQueries"], cfg["igAccounts"], log, progress, max_age_days=60,
                    start=store.state.get("igNext", 0))
                # results accumulate across runs (each run only does a batch of searches);
                # expired posts drop out via validUntil
                seen = store.state.get("seen", {})
                for o in found:
                    o["firstSeen"] = seen.get(o["id"], t.isoformat())
                    _stamp(o, "instagram", cfg, t)
                new_ids = {o["id"] for o in found}
                kept = [o for o in store.by_source("instagram") if o["id"] not in new_ids]
                store.put("instagram", kept + [o for o in found if _live(o, t)], ok=not blocked,
                          note="DuckDuckGo rate-limited this run" if blocked else "")

            elif src == "news":
                found = news.collect(log, days=30)
                for o in found:
                    _stamp(o, "news", cfg, t)
                store.put("news", [o for o in found if _live(o, t)])
        except Exception as e:
            failed.append(src)
            log(f"{src}: failed — {e} (keeping previous offers until they expire)")
            traceback.print_exc()
            store.put(src, [o for o in store.by_source(src) if _live(o, t)], ok=False, note=str(e)[:200])
    log(f"Done. {len(store.db['offers'])} live offers" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return failed
