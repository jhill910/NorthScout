"""Try every route into Bluesky and report which, if any, works.

WHY
---
public.api.bsky.app/xrpc returns HTTP 403 from two independent networks --
a Fox corporate desktop and a GitHub Actions runner. So it is not a corporate
filter and it is not the User-Agent. Something about that endpoint refuses
this traffic.

There are several other doors into the same data. This script knocks on all of
them and tells you which opened, so the fix is evidence rather than guesswork.

    python probe_social.py                      # unauthenticated routes
    python probe_social.py --handle you.bsky.social --app-password xxxx-xxxx

The app password is optional and only used for route 4. Bluesky app passwords
are revocable, scoped tokens created at Settings -> App Passwords; they are not
your account password. Nothing is written to disk by this script.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 20

# A handle only used to test profile-scoped routes. Bluesky's own account is
# a safe, certainly-existing target.
TEST_HANDLE = "bsky.app"


def _try(label, url, headers=None, expect="json"):
    """Return (ok, detail). Never raises."""
    h = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(4000)
            status = r.status
        if expect == "json":
            try:
                json.loads(body.decode("utf-8", "replace"))
                return True, f"HTTP {status}, valid JSON"
            except json.JSONDecodeError:
                return False, f"HTTP {status} but body is not JSON"
        head = body[:200].decode("utf-8", "replace").replace("\n", " ")
        if "<rss" in head or "<feed" in head or "<?xml" in head:
            return True, f"HTTP {status}, XML feed"
        return False, f"HTTP {status}, not a feed ({head[:60]}...)"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, type(e).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", help="your Bluesky handle, for the authenticated test")
    ap.add_argument("--app-password", help="a Bluesky APP password (not your login password)")
    args = ap.parse_args()

    q = urllib.parse.urlencode({"q": '"Green Bay Packers"', "limit": "3"})
    routes = [
        ("1. public API (what we use now)",
         f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?{q}", None, "json"),
        ("2. api.bsky.app",
         f"https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?{q}", None, "json"),
        ("3. bsky.social PDS host",
         f"https://bsky.social/xrpc/app.bsky.feed.searchPosts?{q}", None, "json"),
        ("4. profile RSS feed",
         f"https://bsky.app/profile/{TEST_HANDLE}/rss", None, "xml"),
        ("5. getAuthorFeed (no search)",
         "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
         f"?actor={TEST_HANDLE}&limit=3", None, "json"),
        ("6. getProfile (lightest possible call)",
         f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={TEST_HANDLE}",
         None, "json"),
    ]

    print("=" * 70)
    print("Bluesky route probe")
    print("=" * 70)
    print()

    working = []
    for label, url, headers, expect in routes:
        ok, detail = _try(label, url, headers, expect)
        print(f"  {'WORKS  ' if ok else 'blocked'}  {label}")
        print(f"            {detail}")
        if ok:
            working.append((label, url))

    # ---- authenticated route ------------------------------------------------
    if args.handle and args.app_password:
        print()
        print("  7. authenticated session (app password)")
        try:
            payload = json.dumps({"identifier": args.handle,
                                  "password": args.app_password}).encode()
            req = urllib.request.Request(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                session = json.loads(r.read().decode())
            jwt = session.get("accessJwt")
            print("            session created OK")
            ok, detail = _try("authed search",
                              f"https://bsky.social/xrpc/app.bsky.feed.searchPosts?{q}",
                              {"Authorization": f"Bearer {jwt}"})
            print(f"  {'WORKS  ' if ok else 'blocked'}  authenticated search")
            print(f"            {detail}")
            if ok:
                working.append(("authenticated search",
                                "https://bsky.social/xrpc/app.bsky.feed.searchPosts"))
        except urllib.error.HTTPError as e:
            print(f"            login failed: HTTP {e.code}")
        except Exception as e:
            print(f"            login failed: {type(e).__name__}")
    else:
        print()
        print("  7. authenticated session — skipped")
        print("     Re-run with --handle and --app-password to test this route.")

    print()
    print("=" * 70)
    if working:
        print(f"{len(working)} route(s) work. The best one:")
        print(f"   {working[0][0]}")
        print(f"   {working[0][1]}")
        print()
        print("Send this output back and I'll point bluesky.py at it.")
    else:
        print("No route works from this machine.")
        print()
        print("If the GitHub Action also finds nothing, Bluesky is simply not")
        print("reachable for this kind of use and the honest move is to stop")
        print("trying. The blogs and wires already carry the reporting; what")
        print("would be lost is the offhand social moment, like the MLB account")
        print("dunking on the Packers -- which is a manual find anyway.")
    return 0 if working else 1


if __name__ == "__main__":
    sys.exit(main())
