"""Promo announcements from Bahrain press (Google News RSS): new-branch openings,
app-wide campaigns (Keeta / Jahez / Talabat), hotel brunch and buffet deals."""
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime

from .cuisine import classify
from .net import UA, get


def resolve_google_news(link):
    """Turn a news.google.com article link into the publisher's URL (same RPC the Google News
    page itself uses). Returns None if Google changes the format — the redirect link still works."""
    if "news.google.com" not in link:
        return link
    try:
        page = get(link, retries=1)
        grab = lambda attr: (re.search(rf'data-n-a-{attr}="([^"]+)"', page) or [None, None])[1]
        aid, ts, sg = grab("id"), grab("ts"), grab("sg")
        if not (aid and ts and sg):
            return None
        inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                                "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], aid, int(ts), sg]
        body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]]))
        req = urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body.encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": UA})
        txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        m = re.search(r'https?://(?!news\.google|www\.google)[^\\"\s]+', txt)
        return m.group(0) if m else None
    except Exception:
        return None

QUERIES = [
    "bahrain restaurant offer", "bahrain restaurant promotion", "bahrain food deal", "bahrain dining offer",
    "bahrain brunch offer", "bahrain buffet offer", "keeta bahrain offer", "jahez bahrain offer",
    "talabat bahrain offer", "bahrain restaurant discount", "bahrain buy one get one",
]
_FOOD = re.compile(r"restaurant|food|dining|dine|brunch|buffet|iftar|suhoor|burger|pizza|cafe|café|coffee|meal|menu|"
                   r"talabat|keeta|jahez|chicken|shawarma|biryani|kitchen|grill|sushi|dessert", re.I)
_DEAL = re.compile(r"offer|deal|promo|discount|% ?off|free|save|buy one|launch|special|price", re.I)
_BH_SOURCES = re.compile(r"news of bahrain|gulf daily news|gdn|daily tribune|bahrain this week|local ?bh|localbh|"
                         r"bna|bahrain news agency|al ayam|alwatan|al bilad|akhbar al khaleej|fact|timeout bahrain", re.I)
_ELSEWHERE = re.compile(r"\b(uae|dubai|abu dhabi|saudi|riyadh|jeddah|qatar|doha|kuwait|oman|muscat|uk|us|india|egypt)\b", re.I)
_NOISE = re.compile(r"covid|booster|visa|oil|stocks?|bank|tourism fee|airline|flight|real estate|job|franchise|signs|acquisition|merger|watchdog|shares|highchair|high chair", re.I)


def collect(log, days=30):
    found = {}
    for q in QUERIES:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{q} when:{days}d")
               + "&hl=en-BH&gl=BH&ceid=BH:en")
        try:
            xml = get(url)
        except Exception as e:
            log(f"News · '{q}' failed: {e}")
            continue
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
            title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", item, re.S) or [None, ""])[1]))
            link = (re.search(r"<link>(.*?)</link>", item, re.S) or [None, ""])[1]
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", item) or [None, ""])[1]
            src = html.unescape((re.search(r"<source[^>]*>(.*?)</source>", item) or [None, ""])[1])
            headline = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
            if not (_FOOD.search(headline) and _DEAL.search(headline)) or _NOISE.search(headline):
                continue
            in_bh = "bahrain" in headline.lower() or "البحرين" in headline
            if not in_bh and (not _BH_SOURCES.search(src) or _ELSEWHERE.search(headline)):
                continue
            key = hashlib.md5(headline.lower().encode()).hexdigest()[:12]
            if key in found:
                continue
            try:
                d = parsedate_to_datetime(pub).date().isoformat()
            except Exception:
                d = None
            chan = "delivery" if re.search(r"talabat|keeta|jahez|deliver", headline, re.I) else "in-person"
            pct = [int(x) for x in re.findall(r"(\d{1,2})\s?%", headline)]
            found[key] = {
                "id": "news:" + key, "source": "news", "channel": chan,
                "restaurant": src or "News", "handle": "", "branch": "",
                "rawCuisines": [], "cuisines": classify(text=headline),
                "title": headline, "detail": f"Reported by {src}" if src else "",
                "items": [], "maxPct": max(pct) if pct else 0,
                "url": link, "image": "", "rating": None, "areas": [], "date": d,
            }
    # Google News links are redirects — swap them for the publisher's own article URL
    resolved = 0
    for o in found.values():
        real = resolve_google_news(o["url"])
        if real:
            o["url"], resolved = real, resolved + 1
    log(f"News: {len(found)} food-offer stories from the last {days} days ({resolved} linked to the publisher)")
    return list(found.values())
