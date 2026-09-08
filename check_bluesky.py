"""Verify the Bluesky accounts and their RSS feeds.

The API search endpoint is refused (HTTP 403 from two independent networks),
so bluesky.py follows named accounts via profile RSS instead. That makes the
handles load-bearing: a wrong handle yields nothing, silently.

This resolves every handle against getProfile (which still works), fetches
each RSS feed, and shows what came back.

    python check_bluesky.py             # report
    python check_bluesky.py --write     # also record results in bluesky.py
"""

import argparse
import sys

import bluesky


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="update STATUS values in bluesky.py to match results")
    args = ap.parse_args()

    accounts = bluesky.ACCOUNTS
    print("=" * 72)
    print("Bluesky account check")
    print("=" * 72)
    print(f"\nChecking {len(accounts)} account(s) via profile RSS.\n")

    width = max(len(a[0]) for a in accounts) + 2
    results = []

    for handle, label, team, status in accounts:
        exists = bluesky.resolve_handle(handle)
        posts = bluesky.profile_feed(handle, label) if exists else []
        results.append((handle, label, exists, len(posts)))

        if not exists:
            mark = "NOT FOUND"
        elif posts:
            mark = f"OK ({len(posts)})"
        else:
            mark = "no recent posts"
        print(f"  {mark:<18} {handle:<{width}} {label}")
        if posts:
            print(f"                     └─ {posts[0]['text'][:64]}")

    found = [r for r in results if r[2]]
    live = [r for r in results if r[3] > 0]

    print()
    print("-" * 72)
    print(f"  {len(found)}/{len(accounts)} handles resolve · "
          f"{len(live)} returning recent posts")

    missing = [r[0] for r in results if not r[2]]
    if missing:
        print()
        print("  These handles do not exist:")
        for h in missing:
            print(f"     {h}")
        print()
        print("  Find the real one on bsky.app and take it from the profile URL:")
        print("     bsky.app/profile/THIS-PART")
        print("  Then edit bluesky.ACCOUNTS and re-run this.")

    if args.write:
        changed = 0
        for handle, label, exists, n in results:
            want = "verified" if exists else "disabled"
            cur = next(a[3] for a in accounts if a[0] == handle)
            if cur != want:
                changed += bluesky.mark_status(handle, want)
        print(f"\n  Updated {changed} STATUS value(s) in bluesky.py")

    print()
    if live:
        print("Bluesky is working. The scrape will pick these up on the next run.")
        return 0
    if found:
        print("Handles resolve but no recent posts. Either the accounts are quiet")
        print("or the RSS shape has changed — check one manually in a browser:")
        print(f"   https://bsky.app/profile/{found[0][0]}/rss")
        return 0
    print("No handles resolved. Nothing will come through until real ones are set.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
