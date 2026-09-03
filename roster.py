"""Self-updating roster of NFC North people, harvested from the feeds.

WHY THIS EXISTS
---------------
`NFC_KEYWORDS` in agent.py was a hand-typed list of 27 names. It gates which
national-show clips (McAfee, The Herd, SportsCenter) count as NFC North
relevant, so anyone missing from the list was invisible. On 2026-09-01 that
included Kaleb Johnson, Clark Phillips III, Gervon Dexter, Braxton Jones,
Coby Bryant, Greg Dortch and Josh Jacobs -- every one of them a topic on that
week's show. A list a human has to remember to update is a list that is always
out of date exactly when it matters, because the players who become newsworthy
are the ones who just arrived.

TWO HARVEST SOURCES
-------------------
1. `<media:keywords>` on club RSS items. Clubs tag their own stories with the
   players involved, which is authoritative and free. Coverage varies: the
   Bears tag players heavily, the Packers mostly tag sections.
2. Capitalised name extraction from headlines and summaries, reusing
   scoring.extract_names(). Catches what the tags miss.

Names accumulate in data/rosters.json across runs with first/last-seen dates,
so the roster survives a player having a quiet week. Anyone unseen for
ROSTER_TTL_DAYS drops off, which handles cuts and trades without manual work.
"""

import json
import os
import re
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ROSTER_PATH = os.path.join(DATA_DIR, "rosters.json")

# Long enough to survive a bye week or a quiet stretch; short enough that a
# player cut in September is gone before December.
ROSTER_TTL_DAYS = 60

TEAMS = ["Chicago Bears", "Detroit Lions", "Green Bay Packers", "Minnesota Vikings"]

# Club feeds mix player tags with CMS section tags in the same field. These
# patterns identify the section tags.
NOISE_PATTERNS = [
    r":",                       # "News: All News", "News: Transactions"
    r"\s-\s",                   # "Article - Roster Moves", "NEWS - Twentyman"
    r"/",                       # "Minicamp / OTAs / Training Camp"
    r"\(\d{4}",                 # "Packers at Broncos (2026-PRE-2)"
    r"\bCP\b",                  # "Homepage CP", "Community CP"
    r"\d",                      # anything with digits
]

NOISE_EXACT = {
    "homepage", "community", "legends", "cheerleaders", "all news",
    "press releases", "transactions", "training camp", "minicamp", "otas",
    "gameday", "stories", "features", "national feature", "insider inbox",
    "five things", "longform", "index", "team", "news", "video", "photos",
    "roster moves", "roster move", "draft", "schedule", "tickets", "shop",
    "podcast", "audio", "game recap", "injury report", "depth chart",
    "practice squad", "free agency", "mailbag", "lunch break", "daily drive",
}

# Words that mean a capitalised phrase is a section, event or place -- not a
# person. Kept separate from scoring.NAME_STOP because the tag vocabulary
# differs from headline vocabulary.
NOISE_WORDS = {
    "bears", "lions", "packers", "vikings", "chicago", "detroit", "green",
    "bay", "minnesota", "nfl", "nfc", "afc", "espn", "fox", "cbs", "nbc",
    "stadium", "field", "hall", "fame", "week", "season", "camp", "bowl",
    "conference", "division", "playoff", "playoffs", "super",
    "presented", "carhartt", "verizon", "bud", "light", "miller", "lite",
    # event / product phrasing that reads like a name in tag fields
    "uniform", "uniforms", "rivalries", "chat", "look", "look-in", "contest",
    "fans", "luncheon", "banquet", "rally", "sweepstakes", "party", "shop",
    "store", "cheer", "cheerleaders", "alumni", "legends", "auction",
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "live", "watch", "listen", "stream", "highlights", "recap", "preview",
    # sentence fragments that survive capitalisation heuristics
    "this", "that", "these", "those", "give", "us", "our", "we", "they",
    "com", "org", "net",
}

_NAME_RE = re.compile(r"^[A-Z][A-Za-z'\-\.]+(?: [A-Z][A-Za-z'\-\.]+){1,2}$")


def normalise(tag):
    """Strip club and position prefixes from a tag: 'QB Kedon Slovis' -> 'Kedon Slovis'.

    Also merges duplicates -- the same player is tagged 'Kedon Slovis' on one
    story and 'QB Kedon Slovis' on the next.
    """
    try:
        import scoring
        tokens = scoring._trim_name((tag or "").strip().split())
        return " ".join(tokens)
    except Exception:
        return (tag or "").strip()


def looks_like_person(tag):
    """True if a media:keywords entry looks like a person's name."""
    t = normalise(tag)
    if not t or len(t) > 40:
        return False
    if t.lower() in NOISE_EXACT:
        return False
    for pat in NOISE_PATTERNS:
        if re.search(pat, t):
            return False
    if not _NAME_RE.match(t):
        return False
    parts = [p.strip(".'-").lower() for p in t.split()]
    if any(p in NOISE_WORDS for p in parts):
        return False
    try:
        import scoring
        if any(p in scoring.NFL_CLUBS or p in scoring.NAME_STOP for p in parts):
            return False
    except Exception:
        pass
    # Single-letter "words" are usually initials in a real name (J.J.), which
    # is fine, but a lone capital is not.
    if all(len(p) <= 1 for p in parts):
        return False
    # URLs and sentence fragments: "ChicagoBears.com. This"
    if any("." in p and p.split(".")[-1] in ("com", "org", "net") for p in t.lower().split()):
        return False
    return True


def extract_from_entry(entry):
    """Names from one feed entry: media:keywords first, then headline text."""
    found = set()

    raw_tags = []
    kw = entry.get("media_keywords") or entry.get("keywords") or ""
    if isinstance(kw, (list, tuple)):
        raw_tags.extend(str(k) for k in kw)
    elif kw:
        raw_tags.extend(str(kw).split(","))
    for tags in entry.get("tags", []) or []:
        term = tags.get("term") if isinstance(tags, dict) else None
        if term:
            raw_tags.extend(str(term).split(","))

    for tag in raw_tags:
        tag = tag.strip()
        if looks_like_person(tag):
            found.add(normalise(tag))

    # Fall back to entity extraction over title + summary.
    try:
        import scoring
        text = f"{entry.get('title','')} {entry.get('summary','')}"
        for name in scoring.extract_names(text):
            if looks_like_person(name):
                found.add(name)
    except Exception:
        pass

    return found


def load_rosters():
    if not os.path.exists(ROSTER_PATH):
        return {t: {} for t in TEAMS}
    try:
        with open(ROSTER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {t: {} for t in TEAMS}
    for t in TEAMS:
        data.setdefault(t, {})
    return data


def save_rosters(rosters):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ROSTER_PATH, "w", encoding="utf-8") as f:
        json.dump(rosters, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def harvest(by_team, rosters=None, today=None):
    """Update rosters from {team: [(entry, source), ...]}. Returns rosters."""
    rosters = rosters if rosters is not None else load_rosters()
    today = (today or datetime.now()).date().isoformat()

    for team, pairs in by_team.items():
        if team not in rosters:
            rosters[team] = {}
        bucket = rosters[team]
        for item in pairs:
            entry = item[0] if isinstance(item, tuple) else item
            for name in extract_from_entry(entry):
                rec = bucket.get(name)
                if rec:
                    rec["last_seen"] = today
                    rec["count"] = rec.get("count", 0) + 1
                else:
                    bucket[name] = {"first_seen": today, "last_seen": today,
                                    "count": 1}
    return rosters


def prune(rosters, ttl_days=ROSTER_TTL_DAYS, today=None):
    """Drop names not seen recently -- handles cuts and trades automatically."""
    cutoff = ((today or datetime.now()) - timedelta(days=ttl_days)).date().isoformat()
    removed = 0
    for team, bucket in rosters.items():
        for name in [n for n, r in bucket.items()
                     if r.get("last_seen", "0000-00-00") < cutoff]:
            del bucket[name]
            removed += 1
    return removed


def all_names(rosters=None, team=None):
    """Lowercased names for keyword matching."""
    rosters = rosters if rosters is not None else load_rosters()
    out = set()
    buckets = [rosters.get(team, {})] if team else rosters.values()
    for bucket in buckets:
        out.update(n.lower() for n in bucket)
    return out


def summary(rosters=None):
    rosters = rosters if rosters is not None else load_rosters()
    return {t: len(rosters.get(t, {})) for t in TEAMS}
