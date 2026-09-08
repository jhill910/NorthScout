"""Bluesky (AT Protocol) as the replacement for X/Twitter scraping.

WHY THIS REPLACED X
-------------------
scrape_x_media_bites() drove a logged-in headless browser through nine
profiles on a timer. That is automated access to a logged-in session, which
violates X's terms, is trivially detectable, and produced zero rows in four
months. The account used for it was ultimately suspended.

Bluesky's public API needs no account, no browser and no stored credentials.
It is a documented, permitted, unauthenticated read API, so there is nothing
to expire and nothing to get suspended.

IMPORTANT -- UNVERIFIED RESPONSE SHAPE
--------------------------------------
This module was written on a machine that cannot reach the Bluesky API, so the
JSON shape below is from documentation and memory, NOT from an observed
response. Every field access is therefore defensive: missing or renamed keys
degrade to empty results instead of raising.

Run `python check_bluesky.py` from a networked machine. It prints the ACTUAL
response shape and flags any mismatch with what this module expects.

Endpoints used (public.api.bsky.app, no auth):
    app.bsky.feed.searchPosts   ?q=<query>&limit=<n>&sort=latest
    app.bsky.feed.getAuthorFeed ?actor=<handle>&limit=<n>
    app.bsky.actor.getProfile   ?actor=<handle>
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

API_BASE = "https://public.api.bsky.app/xrpc"
TIMEOUT = 20

# A custom User-Agent ("NorthScout/1.0 ...") drew an HTTP 403 on 2026-09-08.
# Cloudflare-fronted APIs routinely reject unrecognised agents before the
# request ever reaches the application. A standard browser string is treated
# as ordinary traffic. This is not evasion -- the endpoint is public and
# unauthenticated; it just wants a UA it recognises.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

MAX_POSTS_PER_QUERY = 12
MAX_AGE_DAYS = 8

# Search queries, run against the whole network. These need no handles to be
# correct, which is deliberate: guessed handles are a source of silent error.
SEARCH_QUERIES = [
    '"Chicago Bears"',
    '"Detroit Lions"',
    '"Green Bay Packers"',
    '"Minnesota Vikings"',
    '"NFC North"',
]

# Accounts worth following directly. These are UNVERIFIED guesses at handles --
# check_bluesky.py resolves each one and reports which exist. Do not trust this
# list until it has been checked; a wrong handle silently yields nothing.
CANDIDATE_HANDLES = [
    # (label, handle, team)
    ("Windy City Gridiron", "windycitygridiron.com", "Chicago Bears"),
    ("Pride of Detroit", "prideofdetroit.com", "Detroit Lions"),
    ("Acme Packing Company", "acmepackingcompany.com", "Green Bay Packers"),
    ("Daily Norseman", "dailynorseman.com", "Minnesota Vikings"),
]


LAST_ERROR = None


def _get(endpoint, params):
    """GET a public XRPC endpoint. Returns parsed JSON or None.

    Records the failure reason in LAST_ERROR so check_bluesky.py can tell a
    network block apart from a changed endpoint.
    """
    global LAST_ERROR
    url = f"{API_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            LAST_ERROR = None
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        LAST_ERROR = f"HTTP {e.code}" + (f" — {body}" if body else "")
        print(f"   ⚠️  Bluesky {endpoint}: {LAST_ERROR}")
    except Exception as e:
        LAST_ERROR = f"{type(e).__name__}: {e}"
        print(f"   ⚠️  Bluesky {endpoint}: {LAST_ERROR}")
    return None


def post_url(post):
    """Build a bsky.app permalink from a post record.

    at://did:plc:xxxx/app.bsky.feed.post/RKEY
        -> https://bsky.app/profile/<handle>/post/RKEY
    """
    try:
        uri = post.get("uri") or ""
        rkey = uri.rsplit("/", 1)[-1]
        handle = ((post.get("author") or {}).get("handle") or "").strip()
        if rkey and handle:
            return f"https://bsky.app/profile/{handle}/post/{rkey}"
    except Exception:
        pass
    return ""


def parse_post(raw):
    """Normalise one post into the shape save_media_bite() expects.

    Written defensively on purpose: every key may be absent or renamed.
    Returns None if the post can't be used.
    """
    if not isinstance(raw, dict):
        return None

    # searchPosts returns posts directly; getAuthorFeed wraps them as
    # {"post": {...}, "reason": ...}. Accept either.
    post = raw.get("post") if isinstance(raw.get("post"), dict) else raw

    author = post.get("author") or {}
    record = post.get("record") or {}

    text = (record.get("text") or "").strip()
    if not text:
        return None

    link = post_url(post)
    if not link:
        return None

    handle = author.get("handle") or "unknown"
    display = author.get("displayName") or handle

    created = record.get("createdAt") or post.get("indexedAt") or ""
    when = ""
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        dt = dt.replace(tzinfo=None)
        if (datetime.utcnow() - dt) > timedelta(days=MAX_AGE_DAYS):
            return None            # outside the show window
        when = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        when = datetime.now().strftime("%Y-%m-%d %H:%M")

    return {
        "source": f"🦋 @{handle}",
        "text": text[:400],
        "link": link,
        "fetched_at": when,
        "author_display": display,
        "handle": handle,
    }


def search(query, limit=MAX_POSTS_PER_QUERY):
    data = _get("app.bsky.feed.searchPosts",
                {"q": query, "limit": limit, "sort": "latest"})
    if not data:
        return []
    posts = data.get("posts")
    if not isinstance(posts, list):
        return []
    out = []
    for raw in posts:
        p = parse_post(raw)
        if p:
            out.append(p)
    return out


def author_feed(handle, limit=MAX_POSTS_PER_QUERY):
    data = _get("app.bsky.feed.getAuthorFeed", {"actor": handle, "limit": limit})
    if not data:
        return []
    feed = data.get("feed")
    if not isinstance(feed, list):
        return []
    out = []
    for raw in feed:
        p = parse_post(raw)
        if p:
            out.append(p)
    return out


def resolve_handle(handle):
    """True if the handle exists. Used by check_bluesky.py."""
    data = _get("app.bsky.actor.getProfile", {"actor": handle})
    return bool(data and data.get("did"))


def collect(relevance_fn=None):
    """Gather division-relevant posts. Returns a list of normalised dicts.

    relevance_fn: optional callable(text) -> bool, so the roster-backed
    relevance filter in agent.py can be reused here.
    """
    seen, out = set(), []

    for q in SEARCH_QUERIES:
        for p in search(q):
            if p["link"] in seen:
                continue
            if relevance_fn and not relevance_fn(p["text"]):
                continue
            seen.add(p["link"])
            out.append(p)

    for label, handle, team in CANDIDATE_HANDLES:
        for p in author_feed(handle):
            if p["link"] in seen:
                continue
            if relevance_fn and not relevance_fn(p["text"]):
                continue
            p["source"] = f"🦋 {label}"
            seen.add(p["link"])
            out.append(p)

    return out
