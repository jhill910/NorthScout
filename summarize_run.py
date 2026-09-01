"""Print a Markdown summary of the current snapshot for the GitHub Actions run page.

Keeps the workflow YAML free of embedded Python heredocs, which are fragile and
awkward to test. Run it locally any time to see the state of the board:

    python summarize_run.py
"""

import json
import os

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "northscout.json")


def main():
    print("### NorthScout scrape\n")

    if not os.path.exists(SNAPSHOT):
        print("🛑 No snapshot produced.")
        return

    try:
        with open(SNAPSHOT, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"🛑 Snapshot unreadable: `{e}`")
        return

    counts = snap.get("counts", {})
    print(f"- Generated: `{snap.get('generated_at', 'unknown')}`")
    print(f"- Window: {snap.get('window_days', '?')} days")
    print(f"- Stories: **{counts.get('team_news', 0)}** · "
          f"Media bites: **{counts.get('media_bites', 0)}**\n")

    print("| Team | Stories | Top-ranked story |")
    print("|---|---:|---|")
    for team, rows in snap.get("team_news", {}).items():
        top = rows[0]["title"][:70].replace("|", "\\|") if rows else "_none_"
        print(f"| {team} | {len(rows)} | {top} |")

    media = snap.get("media_bites", [])
    if media:
        yt = sum(1 for m in media if m.get("platform") == "youtube")
        x = sum(1 for m in media if m.get("platform") == "x")
        print(f"\n**Media:** {yt} YouTube · {x} X/Twitter")
        if x == 0:
            print("\n> ⚠️ No X posts captured. The `X_AUTH_JSON` secret is either "
                  "missing or the saved session has expired.")


if __name__ == "__main__":
    main()
