"""Scrape the division and write a durable JSON snapshot.

WHY THIS EXISTS
---------------
Streamlit Community Cloud runs on an ephemeral filesystem. Anything the app
writes to disk -- including northscout.db -- is destroyed on restart, redeploy
or inactivity sleep. That is why hitting "Sync Live Data Now" appeared to work
and then silently reverted to weeks-old stories.

The fix is to move the scrape off the web dyno entirely. A scheduled GitHub
Action runs this script, and commits data/northscout.json back to the repo.
The repo is durable, so the app always has fresh data to read even on a
cold-started container.

Running this locally is safe and does the same thing.

    python export_json.py
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import agent
import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "northscout.json")

TEAMS = ["Chicago Bears", "Detroit Lions", "Green Bay Packers", "Minnesota Vikings"]


def seed_from_previous_snapshot():
    """Load the last committed snapshot into SQLite before scraping.

    RSS feeds are short. A story published Monday can fall off the feed by
    Friday while still being inside the 8-day show window. Seeding from the
    previous snapshot means the board accumulates across runs instead of
    being limited to whatever happens to be in the feed at this moment.

    Dedupe is on link, so re-inserting known stories is a no-op.
    """
    if not os.path.exists(SNAPSHOT_PATH):
        print("ℹ️  No previous snapshot — starting fresh")
        return 0

    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Could not read previous snapshot ({e}) — starting fresh")
        return 0

    restored = 0
    for team, rows in snap.get("team_news", {}).items():
        for r in rows:
            if not r.get("link"):
                continue
            database.save_team_news_with_media(
                team,
                r.get("title", ""),
                r.get("summary", ""),
                r["link"],
                r.get("fetched_at", ""),
                r.get("thumbnail", ""),
                r.get("score", 0),
                r.get("reasons", ""),
            )
            restored += 1

    for r in snap.get("media_bites", []):
        if not r.get("link"):
            continue
        database.save_media_bite(
            r.get("source", ""),
            r.get("tweet_text", ""),
            r["link"],
            r.get("fetched_at", ""),
            r.get("platform", "youtube"),
            r.get("kind", "clip"),
            r.get("speaker", ""),
        )
        restored += 1

    print(f"♻️  Restored {restored} row(s) from previous snapshot")
    return restored


def prune_stale_team_news(max_age_days=agent.MAX_AGE_DAYS):
    """Drop stories that have aged out of the show window.

    Without this the seed step would accumulate forever, since nothing else
    deletes from team_news.
    """
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fetched_at FROM team_news")
    cutoff = datetime.now() - timedelta(days=max_age_days)

    stale = []
    for row_id, fetched_at in cursor.fetchall():
        parsed = database._parse_media_timestamp(fetched_at)
        # Unparseable dates are KEPT. Dropping them would silently delete
        # stories whose feed used an unusual date format.
        if parsed and parsed < cutoff:
            stale.append(row_id)

    if stale:
        cursor.executemany("DELETE FROM team_news WHERE id = ?", [(i,) for i in stale])
        conn.commit()
    conn.close()
    if stale:
        print(f"🧹 Pruned {len(stale)} story(ies) older than {max_age_days} days")
    return len(stale)


def build_snapshot():
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()

    team_news = {}
    total_stories = 0
    for team in TEAMS:
        cursor.execute(
            """SELECT title, summary, link, fetched_at, thumbnail,
                      COALESCE(score, 0), COALESCE(reasons, '')
               FROM team_news WHERE team = ?
               ORDER BY COALESCE(score, 0) DESC, id DESC""",
            (team,),
        )
        rows = [
            {
                "title": t,
                "summary": s,
                "link": l,
                "fetched_at": f,
                "thumbnail": th,
                "score": round(float(sc), 2),
                "reasons": rz,
            }
            for t, s, l, f, th, sc, rz in cursor.fetchall()
        ]
        team_news[team] = rows
        total_stories += len(rows)

    cursor.execute(
        """SELECT source, tweet_text, link, fetched_at, COALESCE(platform, ''),
                  COALESCE(kind, 'clip'), COALESCE(speaker, '')
           FROM media_bites ORDER BY id DESC"""
    )
    media = [
        {"source": src, "tweet_text": txt, "link": l, "fetched_at": f,
         "platform": p, "kind": k, "speaker": sp}
        for src, txt, l, f, p, k, sp in cursor.fetchall()
    ]
    conn.close()

    try:
        import roster
        roster_counts = roster.summary()
    except Exception:
        roster_counts = {}

    # Embedded so the app gets standings from the same committed file, rather
    # than depending on a second network call at page load.
    try:
        import standings
        standings_snap = standings.refresh()
    except Exception as e:
        print(f"   ⚠️  standings refresh failed ({type(e).__name__})")
        standings_snap = None

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": agent.MAX_AGE_DAYS,
        "counts": {"team_news": total_stories, "media_bites": len(media),
                   "pressers": sum(1 for m in media if m.get("kind") == "presser")},
        "roster_counts": roster_counts,
        "standings": standings_snap,
        "team_news": team_news,
        "media_bites": media,
    }


def main():
    print("=" * 60)
    print(f"NorthScout snapshot — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    print("=" * 60)

    database.init_db()
    seed_from_previous_snapshot()

    agent.main()

    prune_stale_team_news()
    snapshot = build_snapshot()

    counts = snapshot["counts"]
    if counts["team_news"] == 0:
        # Refuse to overwrite a good snapshot with an empty one. A transient
        # network failure should not wipe the producer's board.
        print("🛑 Scrape produced 0 stories — refusing to overwrite the snapshot")
        return 1

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("-" * 60)
    for team, rows in snapshot["team_news"].items():
        top = rows[0]["title"][:52] if rows else "(none)"
        print(f"  {team:<20} {len(rows):>3} stories   top: {top}")
    print("-" * 60)
    print(f"✅ Wrote {SNAPSHOT_PATH}")
    print(f"   {counts['team_news']} stories, {counts['media_bites']} media bites, "
          f"{counts.get('pressers', 0)} presser(s)")
    rc = snapshot.get("roster_counts") or {}
    if rc:
        print("   Roster: " + ", ".join(f"{k.split()[-1]} {v}" for k, v in rc.items()))
    sd = (snapshot.get("standings") or {}).get("teams") or {}
    if sd:
        print("   Standings: " + ", ".join(
            f"{k.split()[-1]} {v.get('record') or '—'}" for k, v in sd.items()))
    else:
        print("   Standings: unavailable this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
