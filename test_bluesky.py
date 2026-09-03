"""Tests for the Bluesky module.

The live API is unreachable from where this was written, so these tests pin
the PARSING contract against representative payloads. If check_bluesky.py shows
the real shape differs, fix parse_post() and these tests will catch fallout.
"""
from datetime import datetime, timedelta
import bluesky

def _post(text="Bears place Kyler Gordon on PUP", handle="brad.bsky.social",
          rkey="3kxyzabc", when=None, display="Brad B"):
    when = when or (datetime.utcnow() - timedelta(hours=3))
    return {"uri": f"at://did:plc:abc123/app.bsky.feed.post/{rkey}",
            "cid": "bafy...",
            "author": {"did": "did:plc:abc123", "handle": handle, "displayName": display},
            "record": {"text": text, "createdAt": when.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}

def test_parses_search_post():
    p = bluesky.parse_post(_post())
    assert p and p["text"].startswith("Bears place")
    assert p["link"] == "https://bsky.app/profile/brad.bsky.social/post/3kxyzabc"
    assert p["source"] == "🦋 @brad.bsky.social"
    print(f"  ok  search post parsed -> {p['link']}")

def test_parses_author_feed_wrapper():
    """getAuthorFeed nests the post one level deeper than searchPosts."""
    p = bluesky.parse_post({"post": _post(), "reason": None})
    assert p and p["link"].endswith("3kxyzabc")
    print("  ok  author-feed wrapper unwrapped")

def test_drops_stale_posts():
    old = _post(when=datetime.utcnow() - timedelta(days=30))
    assert bluesky.parse_post(old) is None
    print("  ok  posts outside the 8-day window dropped")

def test_survives_malformed_payloads():
    """The response shape is unverified, so nothing may raise."""
    for bad in [None, {}, [], "string", 42,
                {"uri": "at://x/y/z"},                       # no author/record
                {"author": {}, "record": {}},                 # empty
                {"uri": "at://a/b/c", "author": {"handle": "h"}, "record": {"text": ""}},
                {"uri": "", "author": {"handle": ""}, "record": {"text": "hi"}},
                {"uri": "at://a/b/k", "author": {"handle": "h"},
                 "record": {"text": "hi", "createdAt": "not-a-date"}}]:
        try:
            bluesky.parse_post(bad)
        except Exception as e:
            raise AssertionError(f"parse_post raised on {bad!r}: {e}")
    # the last one has an unparseable date but valid text/link -> should survive
    ok = bluesky.parse_post({"uri": "at://a/b/k", "author": {"handle": "h"},
                             "record": {"text": "hi", "createdAt": "not-a-date"}})
    assert ok is not None
    print("  ok  malformed payloads degrade instead of raising")

def test_relevance_filter_applied():
    calls = []
    def rel(t):
        calls.append(t); return "Packers" in t
    # unique links per query, otherwise dedupe (correctly) collapses them
    bluesky.search = lambda q, limit=None: [
        {"source":"s","text":"Packers sign a tackle","link":f"https://bsky.app/a/post/{abs(hash(q))}a","fetched_at":"x"},
        {"source":"s","text":"Chiefs sign a kicker","link":f"https://bsky.app/a/post/{abs(hash(q))}b","fetched_at":"x"}]
    bluesky.author_feed = lambda h, limit=None: []
    out = bluesky.collect(relevance_fn=rel)
    assert len(out) == len(bluesky.SEARCH_QUERIES), len(out)   # one kept per query
    assert all("Packers" in o["text"] for o in out)
    assert calls, "relevance_fn never called"
    print(f"  ok  relevance filter applied, AFC post excluded ({len(out)} kept)")

def test_dedupes_across_queries():
    dup = {"source":"s","text":"Packers news","link":"https://bsky.app/a/post/same","fetched_at":"x"}
    bluesky.search = lambda q, limit=None: [dict(dup)]
    bluesky.author_feed = lambda h, limit=None: []
    out = bluesky.collect()
    assert len(out) == 1, f"expected 1 after dedupe, got {len(out)}"
    print("  ok  same post across multiple queries deduped by link")

def test_no_credentials_anywhere():
    src = open("bluesky.py", encoding="utf-8").read().lower()
    for bad in ["password", "auth_token", "ct0", "storage_state", "playwright", "cookie"]:
        assert bad not in src, f"bluesky.py references {bad}"
    print("  ok  no credentials, cookies or browser automation in the module")

if __name__ == "__main__":
    print("bluesky tests")
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn,"__name__","").startswith("test_"): fn()
    print("\nALL TESTS PASSED")
