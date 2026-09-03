"""Capture a fresh X/Twitter session for the scraper.

WHY YOU NEED THIS
-----------------
scrape_x_media_bites() authenticates with saved browser cookies. The existing
twitter_auth.json holds only ONE cookie (auth_token). X also needs ct0, its
CSRF token, so the scraper hits a login wall and quietly gives up -- which is
why media_bites has never contained a single X post.

This opens a real browser, waits for you to log in yourself, then saves the
COMPLETE session state. Your password is never seen by this script or stored
anywhere; only the resulting cookies are written to disk.

USAGE
    python save_x_session.py

Then follow the printed instructions. When it finishes:
    - twitter_auth.json is rewritten locally (already gitignored)
    - copy its full contents into the GitHub secret X_AUTH_JSON

SECURITY
Anyone holding this file can act as you on X. It is in .gitignore, and the
GitHub Action deletes it after every run so it never reaches a commit. Do not
paste it anywhere else.
"""

import json
import os
import sys

AUTH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "twitter_auth.json")

# Without these two, X treats the browser as logged out.
REQUIRED_COOKIES = {"auth_token", "ct0"}


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright isn't installed. Run:\n")
        print("    pip install playwright")
        print("    python -m playwright install chromium\n")
        return 1

    print("=" * 68)
    print("Capturing an X/Twitter session for NorthScout")
    print("=" * 68)
    print()
    print("A browser window will open at x.com.")
    print()
    print("  1. Log in as normal (including any 2FA).")
    print("  2. Wait until your timeline is fully loaded.")
    print("  3. Come back HERE and press Enter.")
    print()
    print("Your password is never read or stored by this script.")
    print()
    input("Press Enter to open the browser... ")

    with sync_playwright() as p:
        # headless=False on purpose: you need to see it to log in.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded")

        print()
        input("Logged in and timeline visible? Press Enter to save the session... ")

        state = context.storage_state()
        browser.close()

    names = {c.get("name") for c in state.get("cookies", [])}
    missing = REQUIRED_COOKIES - names

    print()
    print(f"Captured {len(state.get('cookies', []))} cookie(s).")
    for req in sorted(REQUIRED_COOKIES):
        print(f"   {'OK     ' if req in names else 'MISSING'}  {req}")

    if missing:
        print()
        print(f"Missing {', '.join(sorted(missing))} — the login probably didn't complete.")
        print("Nothing was written. Run this again and make sure your timeline loads.")
        return 1

    with open(AUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    print()
    print(f"Saved to {AUTH_PATH}")
    print()
    print("NEXT STEPS")
    print("  Local:  python export_json.py   (X posts should now appear)")
    print("  Cloud:  copy the ENTIRE contents of twitter_auth.json into")
    print("          GitHub -> Settings -> Secrets and variables -> Actions")
    print("          -> New repository secret, named exactly:  X_AUTH_JSON")
    print()
    print("This file is gitignored and the Action deletes it after each run,")
    print("so it will not reach a commit. Treat it like a password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
