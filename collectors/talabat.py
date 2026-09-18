"""Talabat Bahrain: every restaurant flagged 'Offers' in the chosen delivery areas,
plus the actual discounted menu items (was/now price) from each restaurant's menu.

Data comes from the __NEXT_DATA__ JSON Talabat embeds in its public web pages.
"""
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .cuisine import classify, primary
from .net import get

BASE = "https://www.talabat.com"
_ND = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _page(path):
    m = _ND.search(get(BASE + path))
    return json.loads(m.group(1))["props"]["pageProps"] if m else None


def areas():
    """All Talabat Bahrain delivery areas: [{id, slug, name}]"""
    html = get(BASE + "/bahrain/sitemap")
    seen, out = set(), []
    for aid, slug in re.findall(r"/bahrain/restaurants/(\d+)/([a-z0-9-]+)", html):
        if aid not in seen:
            seen.add(aid)
            out.append({"id": aid, "slug": slug, "name": slug.replace("-", " ").title()})
    return sorted(out, key=lambda a: a["name"])


def _offer_vendors(area, log, max_pages, passes=3):
    """Page through the area's ?filter=Offers listing. Talabat's ordering shuffles between
    requests (sponsored slots), so we read a couple of extra pages and de-dupe."""
    vendors = {}
    base = f"/bahrain/restaurants/{area['id']}/{area['slug']}"
    # Talabat intermittently ignores ?filter=Offers and returns the whole area. Learn the
    # unfiltered size, then only accept pages whose total is clearly smaller (filter applied).
    everything = _page(base)["data"]["totalVendors"]
    first, total = None, None
    for _ in range(6):
        d = _page(f"{base}?filter=Offers")
        if d and d["data"]["totalVendors"] < 0.9 * everything:
            first, total = d, d["data"]["totalVendors"]
            break
        time.sleep(2)
    if not first:
        log(f"Talabat · {area['name']}: offers filter unavailable right now — skipped")
        return vendors
    pages = min(max_pages, -(-total // 15))
    log(f"Talabat · {area['name']}: {total} restaurants with offers")

    def grab(p):
        for _ in range(4 if passes > 1 else 2):
            d = _page(f"{base}?filter=Offers&page={p}")
            data = (d or {}).get("data", {})
            if data.get("totalVendors") == total:
                return data.get("vendors", [])
        return []  # filter kept being ignored for this page; later passes will cover it

    seen_ids = set()  # every listing (incl. groceries) — used to judge coverage against totalVendors

    def take(vs):
        for v in vs:
            seen_ids.add(v["restaurantId"])
            if not v.get("isGrocery") and not v.get("isDarkstore"):
                vendors.setdefault(v["restaurantId"], v)

    take(first["data"]["vendors"])
    # Ordering shuffles on every request, so one pass misses ~20%. Keep sweeping until
    # ~97% of the advertised total has been seen (or 3 passes).
    for sweep in range(passes):
        with ThreadPoolExecutor(4) as ex:
            for fut in as_completed([ex.submit(grab, p) for p in range(1 if sweep else 2, pages + 1)]):
                try:
                    take(fut.result())
                except Exception as e:
                    log(f"  page failed: {e}")
        if len(seen_ids) >= 0.97 * total:
            break
    log(f"Talabat · {area['name']}: saw {len(seen_ids)}/{total} after {sweep + 1} pass(es)")
    return vendors


def _menu_offer(v, area):
    d = _page(f"{v['menuUrl']}?aid={area['id']}")
    if not d:
        return None
    st = d["initialMenuState"]
    seen, items = set(), []
    for it in st["menuData"].get("items", []):
        was, now = it.get("oldPrice") or -1, it.get("price") or 0
        if was <= 0 or now <= 0 or was <= now:
            continue
        key = (it["name"].strip().lower(), now)
        if key in seen:
            continue
        seen.add(key)
        name = it["name"].strip()
        items.append({
            "name": name, "was": round(was, 3), "now": round(now, 3),
            "pct": round(100 * (was - now) / was),
            "desc": (it.get("description") or "").strip()[:160],
            "img": it.get("image") or it.get("originalImage") or "",
            "cuisines": classify(text=name),
        })
    items.sort(key=lambda i: (-i["pct"], i["now"]))
    promos = [p.get("title") or p.get("description") for p in st.get("promotions") or [] if isinstance(p, dict)]
    promos = [p for p in promos if p]
    for t in (v.get("promotionText"), v.get("discountText")):
        if t:
            promos.append(t)
    if not items and not promos:
        # Listed under "Offers" but the deal isn't on menu items (e.g. voucher / free-delivery campaign)
        promos = ["Talabat offer running (voucher or delivery deal — see the app)"]

    labels = [c["name"] for c in v.get("cuisines") or []] or (v.get("cuisineString") or "").split(",")
    if items:
        pcts = sorted({i["pct"] for i in items})
        title = (f"{pcts[-1]}% off" if len(pcts) == 1 else f"Up to {pcts[-1]}% off") + \
                f" · {len(items)} item{'s' if len(items) != 1 else ''}"
    else:
        title = promos[0]
    return {
        "id": f"talabat:{v['restaurantId']}",
        "source": "talabat",
        "channel": "delivery",
        "restaurant": re.sub(r",\s*[^,]+$", "", v["name"]) if "," in v["name"] else v["name"],
        "branch": v.get("branchName") or "",
        "rawCuisines": [l.strip() for l in labels if l.strip()],
        "cuisines": classify(labels, v["name"]),
        "primary": primary([l.strip() for l in labels if l.strip()], v["name"]),
        "title": title,
        "detail": " · ".join(promos) if items and promos else "",
        "items": items,
        "maxPct": items[0]["pct"] if items else 0,
        "url": BASE + v["menuUrl"] + f"?aid={area['id']}",
        "image": v.get("logo") or "",
        "rating": v.get("rate"),
        "deliveryFee": v.get("deliveryFee"),
        "deliveryTime": v.get("avgDeliveryTime") or "",
        "areas": [area["name"]],
        "date": None,
    }


def collect(area_list, log, progress, previous=None, partial=None, max_pages=80):
    """previous: {offer id: offer} from the last run — reused when a menu can't be fetched,
    as long as the restaurant is still listed under Offers. partial(list) is called every
    ~150 menus so results show up in the UI while the run continues."""
    previous = previous or {}
    by_rest = {}   # restaurantId -> (vendor, area it was first seen in)
    area_hits = {}
    for n, a in enumerate(area_list):
        try:
            # Offer restaurants are ~90% the same in every area, so only the first area gets the
            # full multi-pass sweep; the rest get one pass to add their extras + "delivers to" tags.
            for rid, v in _offer_vendors(a, log, max_pages, passes=3 if n == 0 else 1).items():
                by_rest.setdefault(rid, (v, a))
                area_hits.setdefault(rid, []).append(a["name"])
        except Exception as e:
            log(f"Talabat · {a['name']} failed: {e}")
    if not by_rest:
        raise RuntimeError("Talabat returned no restaurants (blocked or offline) — keeping previous results")
    log(f"Talabat: {len(by_rest)} unique restaurants with offers — reading menus (~{len(by_rest) // 180 + 1} min)")

    out, done, total, failed, reused = [], 0, len(by_rest), 0, 0
    with ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(_menu_offer, v, a): rid for rid, (v, a) in by_rest.items()}
        for fut in as_completed(futs):
            rid = futs[fut]
            done += 1
            progress(done, total)
            try:
                o = fut.result()
            except Exception:
                failed += 1
                o = previous.get(f"talabat:{rid}")
                reused += bool(o)
            if o:
                o["areas"] = area_hits[rid]
                out.append(o)
            if partial and done % 150 == 0:
                partial(list(out))
    log(f"Talabat: {len(out)} offers, {sum(len(o['items']) for o in out)} discounted items"
        + (f" ({failed} menus failed, {reused} filled from last run)" if failed else ""))
    return out
