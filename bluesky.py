"""Bluesky via profile RSS feeds.

WHY RSS AND NOT THE API
-----------------------
A route probe on 2026-09-08, run from a Fox desktop, found:

    public.api.bsky.app/xrpc/searchPosts    HTTP 403
    api.bsky.app/xrpc/searchPosts           HTTP 403
    bsky.social/xrpc/searchPosts            HTTP 401
    bsky.app/profile/<handle>/rss           HTTP 200, XML   <- works
    xrpc/app.bsky.actor.getProfile          HTTP 200, JSON  <- works

The same 403 appeared from a GitHub Actions runner, so it is not a corporate
filter and not the User-Agent. Search is simply refused for this kind of
traffic.

Profile RSS is not an API, is not rate-limited the same way, and returns plain
XML that feedparser already handles -- the same library the rest of the
project uses for club feeds. So Bluesky becomes just another RSS source.

The trade-off: no search. We follow named accounts rather than querying the
whole network, which is closer to how the X integration was meant to work.

VERIFY BEFORE TRUSTING
----------------------
The handles below are UNVERIFIED guesses. getProfile still works, so
check_bluesky.py resolves every one and tells you which are real. A wrong
handle yields nothing silently, which is the failure mode worth avoiding.

    python check_bluesky.py
"""

import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

RSS_BASE = "https://bsky.app/profile/{handle}/rss"
PROFILE_API = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
TIMEOUT = 20

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

MAX_POSTS_PER_ACCOUNT = 10
MAX_AGE_DAYS = 8

# Accounts to follow. Handle first, label second.
#
# STATUS: "verified" means check_bluesky.py resolved it against getProfile.
# Everything else is a guess and may be wrong -- SB Nation sites commonly use
# their domain as a handle, but that is a pattern, not a fact.
#
# To add an account: find it on bsky.app, take the handle from the profile URL
# (bsky.app/profile/THIS-PART), add a row, then run check_bluesky.py.
ACCOUNTS = [
    # (handle, label, team, status)
    ("windycitygridiron.com", "Windy City Gridiron", "Chicago Bears", "unverified"),
    ("prideofdetroit.com", "Pride of Detroit", "Detroit Lions", "unverified"),
    ("acmepackingcompany.com", "Acme Packing Company", "Green Bay Packers", "unverified"),
    ("dailynorseman.com", "Daily Norseman", "Minnesota Vikings", "unverified"),
    ("profootballtalk.nbcsports.com", "ProFootballTalk", "division", "unverified"),
]

LAST_ERROR = None


def _fetch(url, accept="application/rss+xml, application/xml, text/xml, */*"):
    """Return raw bytes, or None. Never raises."""
    global LAST_ERROR
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            LAST_ERROR = None
            return resp.read()
    except urllib.error.HTTPError as e:
        LAST_ERROR = f"HTTP {e.code}"
    except Exception as e:
        LAST_ERROR = f"{type(e).__name__}: {e}"
    return None


def resolve_handle(handle):
    """True if the handle exists. Uses getProfile, which the probe found working."""
    import json
    url = PROFILE_API + "?" + urllib.parse.urlencode({"actor": handle})
    raw = _fetch(url, accept="application/json")
    if not raw:
        return False
    try:
        return bool(json.loads(raw.decode("utf-8", "replace")).get("did"))
    except (ValueError, AttributeError):
        return False


def parse_entry(entry, handle, label):
    """Normalise one RSS item into the shape save_media_bite() expects.

    Bluesky's RSS puts the post text in the title, sometimes also in the
    description. Both are read defensively -- the format is not contractual.
    """
    text = (entry.get("title") or "").strip()
    if not text or text.lower().startswith("post by"):
        # Some generators use a placeholder title and put the body elsewhere.
        text = (entry.get("summary") or entry.get("description") or "").strip()
    if not text:
        return None

    link = (entry.get("link") or "").strip()
    if not link:
        return None

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    published = entry.get("published") or entry.get("updated") or ""
    if published:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(published).replace(tzinfo=None)
            if (datetime.utcnow() - dt) > timedelta(days=MAX_AGE_DAYS):
                return None
            when = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    import re
    clean = re.sub("<[^<]+?>", "", text).strip()
    if not clean:
        return None

    return {
        "source": f"🦋 {label}",
        "text": clean[:400],
        "link": link,
        "fetched_at": when,
        "author_display": label,
        "handle": handle,
    }


def profile_feed(handle, label, limit=MAX_POSTS_PER_ACCOUNT):
    """Recent posts from one account's RSS feed."""
    try:
        import feedparser
    except ImportError:
        print("   ⚠️  feedparser not installed — skipping Bluesky")
        return []

    raw = _fetch(RSS_BASE.format(handle=urllib.parse.quote(handle)))
    if not raw:
        print(f"   ⚠️  Bluesky @{handle}: {LAST_ERROR}")
        return []

    try:
        feed = feedparser.parse(raw)
    except Exception as e:
        print(f"   ⚠️  Bluesky @{handle}: unparseable ({type(e).__name__})")
        return []

    out = []
    for entry in (feed.entries or [])[:limit]:
        p = parse_entry(entry, handle, label)
        if p:
            out.append(p)
    return out


def active_accounts(include_unverified=True):
    out = []
    for handle, label, team, status in ACCOUNTS:
        if status == "disabled":
            continue
        if status == "unverified" and not include_unverified:
            continue
        out.append((handle, label, team, status))
    return out


def collect(relevance_fn=None):
    """Gather division-relevant posts across all followed accounts."""
    seen, out = set(), []
    for handle, label, team, status in active_accounts():
        for p in profile_feed(handle, label):
            if p["link"] in seen:
                continue
            # Team accounts are inherently relevant; the division-wide wire
            # still has to mention somebody from the NFC North.
            if team == "division" and relevance_fn and not relevance_fn(p["text"]):
                continue
            seen.add(p["link"])
            out.append(p)
    return out


def mark_status(handle, status):
    """Rewrite this file's STATUS for an account. Used by check_bluesky.py."""
    import os
    import re as _re

    path = os.path.abspath(__file__)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = _re.compile(
        r'(\("' + _re.escape(handle) + r'",\s*"[^"]+",\s*"[^"]+",\s*")'
        r'(verified|unverified|disabled)(")')
    new_text, n = pattern.subn(lambda m: m.group(1) + status + m.group(3), text)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
    return n
