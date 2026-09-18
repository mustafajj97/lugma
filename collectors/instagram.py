"""Instagram offer posts, found through DuckDuckGo's HTML search.

Instagram itself is login-walled, but search engines index public posts with the
caption, account and date in the snippet — that's enough to surface the offer and
link straight to the post. Mostly dine-in / pickup deals restaurants announce there.
"""
import hashlib
import html
import random
import re
import time
import urllib.parse
from datetime import date, datetime, timedelta

from .cuisine import ORDER, classify
from .net import get

DDG = "https://html.duckduckgo.com/html/?q="
_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")  # invisible text-direction marks
_RES = re.compile(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', re.S)
_META = re.compile(r"^(?:[\d,.]+[KM]? likes?, [\d,.]+[KM]? comments? - )?([\w.]+) on ([A-Z][a-z]+ \d{1,2}, \d{4})\W*:?\s*", re.S)
_OFFER = re.compile(
    r"(\d{1,2}\s?%|% ?off|\boff\b|buy\s?(1|one)\s?get|\bb1g1\b|bogo|2\s?for\s?1|\bfree\b|\bdeal\b|\boffer|\bpromo|discount|"
    r"\bonly\s+(bd|bhd)|\b(bd|bhd)\s?\d|\d(\.\d+)?\s?(bd|bhd)\b|happy hour|combo|unlimited|all you can eat|"
    r"عرض|عروض|خصم|مجان|اشتر|فقط|دينار|د\.ب)", re.I)
_BAHRAIN = re.compile(r"bahrain|bh\b|\.bh|manama|seef|juffair|riffa|muharraq|adliya|amwaj|saar|budaiya|isa town|hamad town|البحرين|المنامة", re.I)
_ELSEWHERE = re.compile(r"\b(dubai|uae|abu dhabi|sharjah|saudi|riyadh|jeddah|dammam|khobar|kuwait|qatar|doha|oman|muscat)\b|الرياض|دبي|الكويت|قطر|جدة", re.I)
_DINEIN = re.compile(r"dine[- ]?in|pick ?up|take ?away|walk[- ]?in|in[- ]store|at our (branch|restaurant)|visit us|داخل المطعم|استلام", re.I)
_DELIV = re.compile(r"talabat|keeta|jahez|deliver|طلبات|توصيل|كيتا|جاهز", re.I)


def default_queries():
    base = ['bahrain restaurant offer', 'bahrain food offer', 'bahrain "buy 1 get 1"', 'bahrain dine in offer',
            'bahrain restaurant "% off"', 'bahrain lunch deal', 'عرض مطعم البحرين', 'عروض مطاعم البحرين']
    per = ["pizza", "burger", "shawarma", "biryani", "pakistani", "indian", "broasted", "sushi", "karak",
           "breakfast", "seafood", "mandi", "grills", "dessert", "coffee", "chinese", "pasta", "lebanese", "turkish"]
    return base + [f"bahrain {c} offer" for c in per]


def _parse_date(s):
    try:
        return datetime.strptime(s, "%B %d, %Y").date()
    except ValueError:
        return None


def _search(q):
    page = get(DDG + urllib.parse.quote("site:instagram.com " + q), retries=1)
    if "anomaly" in page.lower() and "result__a" not in page:
        raise RuntimeError("DuckDuckGo rate-limited this run")
    out = []
    for href, title, snip in _RES.findall(page):
        href = html.unescape(href)
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&rut=", 1)[0])
        out.append((href, re.sub(r"<[^>]+>", "", html.unescape(title)).strip(),
                    re.sub(r"<[^>]+>", "", html.unescape(snip)).strip()))
    return out


def _to_offer(href, title, snip, max_age_days):
    if not re.search(r"instagram\.com/(p|reel|reels)/", href):
        return None  # profile pages have no offer content
    m = _META.match(snip)
    account, posted, caption = None, None, snip
    if m:
        account, posted, caption = m.group(1), _parse_date(m.group(2)), snip[m.end():]
    else:
        ma = re.search(r"instagram\.com/([\w.]+)/(?:p|reel)/", href)
        account = ma.group(1) if ma else None
        mt = re.match(r"^([^|:]+?)\s+on\s+Instagram", title)
        if not account and mt:
            account = mt.group(1).strip()
    caption = caption.strip().strip('"“”').strip()
    if posted and posted < date.today() - timedelta(days=max_age_days):
        return None
    title, caption = _BIDI.sub("", title), _BIDI.sub("", caption)
    text = f"{title} {caption}"
    # hashtags like #offer #deals are used on everything — the offer must be in the words themselves
    if not _OFFER.search(re.sub(r"#\S+", " ", text)):
        return None
    # every query already contains "bahrain"; only drop posts that clearly belong elsewhere
    if _ELSEWHERE.search(text) and not _BAHRAIN.search(text + " " + (account or "")):
        return None
    dine, deliv = bool(_DINEIN.search(text)), bool(_DELIV.search(text))
    channel = "both" if dine and deliv else "in-person" if dine else "delivery" if deliv else "in-person"
    pct = [int(x) for x in re.findall(r"(\d{1,2})\s?%", text) if 5 <= int(x) <= 90]
    if re.search(r"buy\s?(1|one)\s?get\s?(1|one)|b1g1|bogo|2\s?for\s?1|1\+1", text, re.I):
        pct.append(50)
    if not account:
        t = re.split(r"\s+(?:on Instagram|\||-|:)", title)[0].strip()
        account = None if not t or t.lower() in ("instagram", "x") else t
    name = (account or "Instagram post").replace("_", " ").replace(".", " ").strip()
    return {
        "id": "ig:" + hashlib.md5(href.split("?")[0].encode()).hexdigest()[:12],
        "source": "instagram",
        "channel": channel,
        "restaurant": name.title() if name.islower() else name,
        "handle": account or "",
        "branch": "",
        "rawCuisines": [],
        "cuisines": classify(text=text + " " + (account or "")),
        "title": caption[:140] + ("…" if len(caption) > 140 else ""),
        "detail": caption,
        "items": [],
        "maxPct": max(pct) if pct else 0,
        "url": href.split("?")[0],
        "image": "",
        "rating": None,
        "areas": [],
        "date": posted.isoformat() if posted else None,
    }


def collect(extra_queries, follow_accounts, log, progress, max_age_days=45, batch=12, start=0):
    """Runs a rotating batch of queries (DDG blocks bursts), always including the user's own
    queries/accounts. Returns (offers, next_start, blocked) — results are merged incrementally.
    If DuckDuckGo blocks the run, the rotation doesn't advance so the next run retries those queries."""
    pool = default_queries()
    rot = [pool[(start + i) % len(pool)] for i in range(min(batch, len(pool)))]
    queries = [q for q in extra_queries if q.strip()] + \
              [f"{h.strip().lstrip('@')} offer" for h in follow_accounts if h.strip()] + rot
    found, total, blocked = {}, len(queries), False
    for i, q in enumerate(queries, 1):
        progress(i, total)
        try:
            for href, title, snip in _search(q):
                o = _to_offer(href, title, snip, max_age_days)
                if o and o["id"] not in found:
                    found[o["id"]] = o
        except RuntimeError as e:
            log(f"Instagram: {e} — stopping early with {len(found)} posts (try again in a few minutes)")
            blocked = True
            break
        except Exception as e:
            log(f"Instagram · '{q}' failed: {e}")
        time.sleep(random.uniform(4, 7))  # be gentle; DDG throttles bursts
    undated = sum(1 for o in found.values() if not o["date"])
    log(f"Instagram: {len(found)} offer posts this run ({undated} without a visible date)")
    return list(found.values()), (start if blocked else (start + batch) % len(pool)), blocked
