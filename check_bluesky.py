"""Verify the Bluesky integration against the live API.

bluesky.py was written without network access to Bluesky, so its assumptions
about the JSON shape are unconfirmed. This script checks them against reality
and tells you exactly what, if anything, is wrong.

    python check_bluesky.py           # check API, shape and handles
    python check_bluesky.py --raw     # also dump one raw post as JSON

If the shape check fails, the fix is in bluesky.parse_post() -- the field names
it reads are listed in the output so you can compare directly.
"""

import argparse
import json
import sys

import bluesky


def check_api():
    print("1. API reachability")
    data = bluesky._get("app.bsky.feed.searchPosts",
                        {"q": '"Green Bay Packers"', "limit": 3, "sort": "latest"})
    if data is None:
        print("   FAIL — no response. Check network, or the endpoint has moved.")
        return None
    print(f"   OK — response received, top-level keys: {list(data.keys())}")
    return data


def check_shape(data, dump_raw=False):
    print("\n2. Response shape")
    posts = data.get("posts")
    if not isinstance(posts, list):
        print(f"   FAIL — expected a list under 'posts', got {type(posts).__name__}")
        print(f"   Actual top-level keys: {list(data.keys())}")
        print("   -> update bluesky.search() to read the correct key")
        return False
    if not posts:
        print("   WARN — 'posts' is empty. Query returned nothing; try again later.")
        return True

    print(f"   OK — {len(posts)} post(s) returned")
    raw = posts[0]
    print(f"   post keys: {sorted(raw.keys())}")
    author = raw.get("author") or {}
    record = raw.get("record") or {}
    print(f"   author keys: {sorted(author.keys())}")
    print(f"   record keys: {sorted(record.keys())}")

    expected = {
        "post.uri": raw.get("uri"),
        "post.author.handle": author.get("handle"),
        "post.author.displayName": author.get("displayName"),
        "post.record.text": record.get("text"),
        "post.record.createdAt": record.get("createdAt"),
    }
    print("\n   fields bluesky.parse_post() relies on:")
    ok = True
    for k, v in expected.items():
        present = v is not None and v != ""
        if not present:
            ok = False
        shown = (str(v)[:52] + "...") if v and len(str(v)) > 52 else v
        print(f"      {'OK     ' if present else 'MISSING'}  {k:<26} {shown}")

    if dump_raw:
        print("\n   raw first post:")
        print(json.dumps(raw, indent=2)[:2000])

    return ok


def check_parsing(data):
    print("\n3. parse_post() output")
    posts = data.get("posts") or []
    parsed = [p for p in (bluesky.parse_post(r) for r in posts) if p]
    if not parsed:
        print("   FAIL — nothing parsed. Either all posts are outside the")
        print("   8-day window, or the field names have changed (see step 2).")
        return False
    print(f"   OK — parsed {len(parsed)}/{len(posts)}")
    for p in parsed[:3]:
        print(f"      {p['source']}  {p['fetched_at']}")
        print(f"        {p['text'][:70]}")
        print(f"        {p['link']}")
    return True


def check_handles():
    print("\n4. Candidate handles")
    print("   These were guesses and have never been verified. A wrong handle")
    print("   yields nothing silently, so anything marked NOT FOUND should be")
    print("   corrected or removed from bluesky.CANDIDATE_HANDLES.\n")
    good = bad = 0
    for label, handle, team in bluesky.CANDIDATE_HANDLES:
        exists = bluesky.resolve_handle(handle)
        good, bad = (good + 1, bad) if exists else (good, bad + 1)
        print(f"   {'FOUND    ' if exists else 'NOT FOUND'}  {handle:<30} {label}")
    print(f"\n   {good} resolved, {bad} not found")
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="dump one raw post")
    args = ap.parse_args()

    print("=" * 66)
    print("Bluesky integration check")
    print("=" * 66 + "\n")

    data = check_api()
    if data is None:
        return 1

    shape_ok = check_shape(data, args.raw)
    parse_ok = check_parsing(data)
    handles_ok = check_handles()

    print("\n" + "=" * 66)
    if shape_ok and parse_ok:
        print("Integration is working." if handles_ok else
              "Integration works; some handles need correcting (search still runs).")
        return 0
    print("Integration needs fixing — see the FAIL/MISSING lines above.")
    print("The field names are read in bluesky.parse_post().")
    return 1


if __name__ == "__main__":
    sys.exit(main())
