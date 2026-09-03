"""Health-check every feed in sources.py and print a table.

Feeds were added from a sandbox that cannot reach third-party sites, so most
are marked "unverified". Run this once from your machine (or let the GitHub
Action run it) to find out which are actually live.

    python check_sources.py            # report only
    python check_sources.py --write    # report, and update STATUS in sources.py

A feed counts as healthy if it parses and returns at least one item. Freshness
is reported separately: a feed that parses but whose newest item is three weeks
old is alive but useless, and you want to see that distinction.
"""

import argparse
import sys
from datetime import datetime

import feedparser

import sources
from scoring import parse_date

TIMEOUT = 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def probe(url):
    """Return (ok, n_items, newest_datetime_or_None, note)."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return False, 0, None, f"HTTP {e.code}"
    except Exception as e:
        return False, 0, None, type(e).__name__

    feed = feedparser.parse(raw)
    entries = feed.entries or []
    if not entries:
        return False, 0, None, "parsed but empty"

    newest = None
    for e in entries:
        dt = parse_date(e.get("published") or e.get("updated") or "")
        if dt and (newest is None or dt > newest):
            newest = dt
    return True, len(entries), newest, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="update STATUS values in sources.py to match results")
    args = ap.parse_args()

    now = datetime.now()
    rows = []
    print(f"Checking {len(sources.SOURCES)} feeds...\n")

    for src in sources.active_sources():
        ok, n, newest, note = probe(src["url"])
        if newest:
            age_d = (now - newest).total_seconds() / 86400
            fresh = f"{age_d:.1f}d old"
            stale = age_d > 14
        else:
            fresh, stale = "no dates", False
        rows.append((src, ok, n, fresh, stale, note))

    w = max(len(r[0]["label"]) for r in rows) + 2
    print(f"  {'FEED':<{w}} {'KIND':<9} {'STATUS':<8} {'ITEMS':>6}  NEWEST")
    print("  " + "-" * (w + 42))
    healthy = dead = stale_n = 0
    for src, ok, n, fresh, stale, note in rows:
        if ok and not stale:
            mark, healthy = "OK  ", healthy + 1
        elif ok:
            mark, stale_n = "STALE", stale_n + 1
        else:
            mark, dead = "DEAD", dead + 1
        detail = fresh if ok else note
        print(f"  {src['label']:<{w}} {src['kind']:<9} {mark:<8} {n:>6}  {detail}")

    print("\n  " + "-" * (w + 42))
    print(f"  {healthy} healthy · {stale_n} stale · {dead} unreachable")

    if dead:
        print("\n  Unreachable feeds are skipped at scrape time with a warning.")
        print("  Re-run with --write to record results in sources.py.")

    if args.write:
        changed = 0
        for src, ok, n, fresh, stale, note in rows:
            want = "verified" if ok else "disabled"
            if src["status"] != want:
                changed += sources.mark_status(src["label"], want)
        print(f"\n  Updated {changed} STATUS value(s) in sources.py")

    # Non-zero exit if every non-official feed is dead -- something systemic.
    non_official = [r for r in rows if r[0]["kind"] != "official"]
    if non_official and not any(r[1] for r in non_official):
        print("\n  WARNING: every non-official feed failed. Check network/DNS.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
