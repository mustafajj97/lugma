"""Works out how long an offer stays valid, so the app never shows expired deals.

Every offer ends up with a `validUntil` date (inclusive). The phone hides anything past it
using its own clock, so stale offers disappear even if a refresh hasn't run.

- Talabat: re-confirmed on every refresh -> valid until 1 day after the last check.
- Instagram / news: end date read from the caption/headline ("until 30 Sept", "ends July 31st",
  "today only", "this weekend", Arabic "حتى 30 سبتمبر" …). If none is stated, a short default
  window after the post date. Recurring deals ("every Monday") get a longer window.
"""
import re
from datetime import date, timedelta

MONTHS = {m: i for i, names in enumerate([
    (), ("jan", "january", "يناير", "كانون الثاني"), ("feb", "february", "فبراير", "شباط"),
    ("mar", "march", "مارس", "آذار"), ("apr", "april", "أبريل", "ابريل", "نيسان"), ("may", "مايو", "أيار"),
    ("jun", "june", "يونيو", "حزيران"), ("jul", "july", "يوليو", "تموز"), ("aug", "august", "أغسطس", "اغسطس", "آب"),
    ("sep", "sept", "september", "سبتمبر", "أيلول"), ("oct", "october", "أكتوبر", "اكتوبر", "تشرين الأول"),
    ("nov", "november", "نوفمبر", "تشرين الثاني"), ("dec", "december", "ديسمبر", "كانون الأول"),
]) for m in names}
_MON = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"

# words that introduce an END date
_END_WORDS = (r"until|till|til|up ?to|ends?(?: on)?|ending|valid (?:until|till|through|thru|to)|expires?(?: on)?|"
              r"through|thru|last day(?: is)?|before|to|–|-|حتى|لغاية|إلى|الى|ينتهي|ينتهى|آخر يوم")
_DATE_FORMS = [
    rf"(?P<d>\d{{1,2}}){_ORD}(?:\s+of)?\s+(?P<m>{_MON})\.?(?:,?\s+(?P<y>20\d\d))?",   # 30 Sept 2026 / 30th of September
    rf"(?P<m2>{_MON})\.?\s+(?P<d2>\d{{1,2}}){_ORD}(?:,?\s+(?P<y2>20\d\d))?",             # Sept 30 / July 31st
    r"(?P<d3>\d{1,2})[/.](?P<m3>\d{1,2})(?:[/.](?P<y3>(?:20)?\d\d))?",                     # 30/9, 30/09/2026 (Bahrain = day first)
]
# numeric dates (30/9) only count after an explicit end word — "serves 2/3" or "- 1/2 price" must not parse
_STRICT_END = (r"until|till|til|ends?(?: on)?|ending|valid (?:until|till|through|thru|to)|expires?(?: on)?|"
               r"last day(?: is)?|حتى|لغاية|ينتهي|ينتهى|آخر يوم")
_END_RX = [re.compile(rf"(?:{_END_WORDS})\s*:?\s*(?:the\s+)?{f}", re.I) for f in _DATE_FORMS[:2]] + \
          [re.compile(rf"(?:{_STRICT_END})\s*:?\s*(?:the\s+)?{_DATE_FORMS[2]}", re.I)]

_TODAY_ONLY = re.compile(r"today only|only today|for today|tonight only|one day only|24 hours only|اليوم فقط|لليوم فقط|ليوم واحد", re.I)
_TOMORROW = re.compile(r"tomorrow only|غدا فقط|بكرة فقط", re.I)
_WEEKEND = re.compile(r"this weekend|weekend only|نهاية الأسبوع|الويكند", re.I)
_THIS_WEEK = re.compile(r"this week only|all week|هذا الأسبوع", re.I)
_THIS_MONTH = re.compile(r"(?:all|this|whole|entire) month|month[- ]long|طوال الشهر|هذا الشهر", re.I)
_RECURRING = re.compile(
    r"\bevery\s+(?:day|mon|tues|wednes|thurs|fri|satur|sun)|\b(?:on\s+)?(?:mon|tues|wednes|thurs|fri|satur|sun)days\b|"
    r"\bdaily\b|\bweekdays\b|\bevery ?day\b|\beach (?:mon|tues|wednes|thurs|fri|satur|sun)day|happy hour|"
    r"كل يوم|يوميا|يومياً|كل (?:سبت|أحد|احد|اثنين|إثنين|ثلاثاء|أربعاء|اربعاء|خميس|جمعة)", re.I)


def _mk(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _resolve(day, month, year, posted):
    """A date without a year belongs to the post's year — or the next one if it would
    otherwise land well before the post (e.g. a December post saying 'until 5 Jan')."""
    if year:
        year = int(year)
        year = year + 2000 if year < 100 else year
        return _mk(year, month, day)
    d = _mk(posted.year, month, day)
    if d and d < posted - timedelta(days=14):
        d = _mk(posted.year + 1, month, day)
    return d


def end_date(text, posted):
    """Stated end date of an offer, or None. `posted` = date the offer was published."""
    if not text:
        return None
    if _TODAY_ONLY.search(text):
        return posted
    if _TOMORROW.search(text):
        return posted + timedelta(days=1)
    found = []
    for rx in _END_RX:
        for m in rx.finditer(text):
            g = m.groupdict()
            if g.get("m"):
                d = _resolve(int(g["d"]), MONTHS[g["m"].lower()], g.get("y"), posted)
            elif g.get("m2"):
                d = _resolve(int(g["d2"]), MONTHS[g["m2"].lower()], g.get("y2"), posted)
            else:
                dd, mm = int(g["d3"]), int(g["m3"])
                if not (1 <= mm <= 12):
                    continue
                d = _resolve(dd, mm, g.get("y3"), posted)
            # ignore nonsense (before the post, or implausibly far out)
            if d and posted - timedelta(days=1) <= d <= posted + timedelta(days=200):
                found.append(d)
    if found:
        return max(found)
    if _WEEKEND.search(text):          # Bahrain weekend = Fri-Sat
        return posted + timedelta(days=(5 - posted.weekday()) % 7)
    if _THIS_WEEK.search(text):
        return posted + timedelta(days=(5 - posted.weekday()) % 7)
    if _THIS_MONTH.search(text):
        nxt = date(posted.year + (posted.month == 12), posted.month % 12 + 1, 1)
        return nxt - timedelta(days=1)
    return None


def is_recurring(text):
    return bool(text and _RECURRING.search(text))


def valid_until(text, posted, default_days, recurring_days=30):
    """(validUntil, how) — `how` explains the date to the user: stated / recurring / assumed."""
    end = end_date(text, posted)
    if end:
        return end, "stated"
    if is_recurring(text):
        return posted + timedelta(days=recurring_days), "recurring"
    return posted + timedelta(days=default_days), "assumed"
