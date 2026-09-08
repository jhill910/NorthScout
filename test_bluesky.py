"""Tests for the Bluesky RSS integration.

The API search endpoint returns 403 from two independent networks, so this
module follows named accounts via profile RSS instead. These tests pin the
RSS parsing contract.
"""
from datetime import datetime, timedelta
from email.utils import format_datetime
import bluesky


def _entry(text="Bears place Kyler Gordon on PUP",
           link="https://bsky.app/profile/x.bsky.social/post/3kabc",
           when=None, summary=None):
    e = {"title": text, "link": link}
    if summary is not None:
        e["summary"] = summary
    e["published"] = format_datetime(when or (datetime.now() - timedelta(hours=3)))
    return e


def test_parses_rss_entry():
    p = bluesky.parse_entry(_entry(), "brad.bsky.social", "Brad B")
    assert p and p["text"].startswith("Bears place")
    assert p["link"].endswith("3kabc")
    assert p["source"] == "🦋 Brad B"
    print("  ok  RSS entry parsed")


def test_falls_back_to_summary():
    """Some generators use a placeholder title and put the text elsewhere."""
    e = _entry(text="Post by @brad.bsky.social", summary="Actual post body here")
    p = bluesky.parse_entry(e, "brad.bsky.social", "Brad B")
    assert p and p["text"] == "Actual post body here", p
    print("  ok  placeholder title falls back to summary")


def test_strips_html():
    e = _entry(text="<p>Gordon to <b>PUP</b></p>")
    p = bluesky.parse_entry(e, "h", "L")
    assert p["text"] == "Gordon to PUP", p["text"]
    print("  ok  HTML stripped from post text")


def test_drops_stale_posts():
    e = _entry(when=datetime.now() - timedelta(days=30))
    assert bluesky.parse_entry(e, "h", "L") is None
    print("  ok  posts outside the 8-day window dropped")


def test_survives_malformed_entries():
    """RSS shape is not contractual — nothing may raise."""
    for bad in [{}, {"title": ""}, {"link": "x"}, {"title": "hi"},
                {"title": "hi", "link": ""},
                {"title": "hi", "link": "u", "published": "not-a-date"},
                {"title": "<p></p>", "link": "u"}]:
        try:
            bluesky.parse_entry(bad, "h", "L")
        except Exception as e:
            raise AssertionError(f"parse_entry raised on {bad!r}: {e}")
    ok = bluesky.parse_entry({"title": "hi", "link": "u", "published": "not-a-date"}, "h", "L")
    assert ok is not None
    print("  ok  malformed entries degrade instead of raising")


def test_relevance_only_applies_to_division_wire():
    """Team accounts are inherently relevant; the wire must mention the division."""
    calls = []
    def rel(t):
        calls.append(t)
        return "Packers" in t
    bluesky.profile_feed = lambda h, l, limit=None: [
        {"source": "s", "text": "Chiefs sign a kicker",
         "link": f"https://bsky.app/{h}/1", "fetched_at": "x"}]
    out = bluesky.collect(relevance_fn=rel)
    teams = {a[2] for a in bluesky.active_accounts()}
    # Every team account keeps its post; the division wire's is filtered out.
    assert all("Chiefs" in o["text"] for o in out)
    assert len(out) == sum(1 for a in bluesky.active_accounts() if a[2] != "division")
    print(f"  ok  relevance filter applied to the wire only ({len(out)} kept)")


def test_no_credentials_or_browser_automation():
    src = open("bluesky.py", encoding="utf-8").read().lower()
    for bad in ["password", "auth_token", "ct0", "storage_state", "playwright", "cookie"]:
        assert bad not in src, f"bluesky.py references {bad}"
    print("  ok  no credentials, cookies or browser automation")


def test_accounts_well_formed():
    for handle, label, team, status in bluesky.ACCOUNTS:
        assert status in ("verified", "unverified", "disabled"), (handle, status)
        assert "/" not in handle and " " not in handle, handle
    print(f"  ok  {len(bluesky.ACCOUNTS)} accounts well-formed")


if __name__ == "__main__":
    print("bluesky RSS tests")
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("\nALL TESTS PASSED")
