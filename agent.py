import feedparser
import re
import os
import random
import time
from collections import Counter
from datetime import datetime
from time import mktime

# Feeds now live in sources.py, which records each one's team, kind and health
# status. The old hardcoded dict was four club PR feeds plus one blog, which is
# why off-field news was structurally unreachable.

IGNORE_WORDS = {"the", "a", "and", "in", "to", "for", "of", "on", "with", "at", "is", "nfc", "north", "teams", "this", "that", "from"}

# Clubs, cities and venues never change, so these stay hardcoded. PEOPLE are
# harvested from the feeds by roster.py -- see is_nfc_north_relevant(). The old
# hand-typed list of 27 names meant anyone who had just arrived was invisible
# to the national-clip filter, which on 2026-09-01 included Kaleb Johnson,
# Clark Phillips III, Gervon Dexter, Coby Bryant and Josh Jacobs. Every one of
# them was a topic on that week's show.
STATIC_KEYWORDS = [
    "bears", "lions", "packers", "vikings", "nfc north", "nfcnorth",
    "chicago", "detroit", "green bay", "minnesota", "halas", "lambeau",
    "soldier field", "ford field", "u.s. bank", "us bank stadium",
]

# Kept as a floor so the filter still works on a cold start, before any roster
# file exists.
CORE_PEOPLE = [
    "caleb williams", "aidan hutchinson", "jordan love", "j.j. mccarthy",
    "jj mccarthy", "ben johnson", "dan campbell", "matt lafleur",
    "kevin o'connell", "kevin oconnell", "ryan poles", "brad holmes",
    "brian gutekunst", "kwesi adofo-mensah",
]

NFC_KEYWORDS = STATIC_KEYWORDS + CORE_PEOPLE   # retained for compatibility

# National / show channels need keyword hits. Team channels are inherently relevant.
NATIONAL_YOUTUBE_FEEDS = {
    "@PatMcAfeeShow": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
    "@TheHerd": "https://www.youtube.com/feeds/videos.xml?channel_id=UCFDidMd82mpDkKijLUqHp7A",
    "@SportsCenter": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiWLfSweyRNmLpgEHekhoAg",
}

# Which club each YouTube channel belongs to, so a presser can be routed onto
# the right team board.
CHANNEL_TEAMS = {
    "Chicago Bears YouTube": "Chicago Bears",
    "Detroit Lions YouTube": "Detroit Lions",
    "Green Bay Packers YouTube": "Green Bay Packers",
    "Minnesota Vikings YouTube": "Minnesota Vikings",
}

TEAM_YOUTUBE_FEEDS = {
    "Chicago Bears YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP0Cdc6moLMyDJiO0s-yhbQ",
    "Detroit Lions YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCv5J06V-ESk5_1uriG65f3w",
    "Green Bay Packers YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJtI-l6La0zniodFtSHYrBg",
    "Minnesota Vikings YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcsw_KrB_wg5lQ5nXWR_LFA",
}

# X/Twitter scraping is DISABLED and should not be re-enabled.
#
# scrape_x_media_bites() drove a logged-in headless browser through nine
# profiles on a timer. That is automated access to a logged-in session: against
# X's terms, trivially detectable, and it produced zero rows in four months.
# The account it used was ultimately suspended (permanent read-only).
#
# bluesky.py replaces it using a public, documented, unauthenticated API. No
# credentials to store, nothing to expire, nobody to get suspended.
X_SCRAPING_DISABLED = True

MAX_AGE_DAYS = 8
MAX_VIDEOS_PER_FEED = 5
MAX_TWEETS_PER_ACCOUNT = 3


# calculate_global_trends() used to live here. It summed, for every headline,
# how often its words appeared across the division, which meant a story's score
# rose with how unremarkable its vocabulary was. Measured against the 2026-09-01
# rundown it surfaced 3 of 13 discussed topics. It is replaced by scoring.py,
# which scores timeliness, availability, transactions, money, decision-maker
# attribution, uncertainty and narrative momentum -- and reached 12 of 13.


# --- Press conferences ----------------------------------------------------
# Every "==" break in the show rundown is a SOT: a clip of a coach or GM
# speaking. The pipeline had no way to find them -- pressers were dumped into
# the same undifferentiated media bucket as hype reels. Clubs post full
# availabilities to YouTube within hours, so they are findable; they just were
# never labelled.

PRESSER_MARKERS = [
    "press conference", "presser", "media availability", "meets the media",
    "speaks with the media", "speaks to the media", "postgame", "post-game",
    "pregame press", "podium", "availability", "full interview",
    "one-on-one", "1-on-1", "sit-down", "addresses the media",
]

# Who is worth tagging by name. Head coach and GM first, then coordinators and
# the quarterbacks -- the voices a producer actually cuts a SOT from.
SPEAKERS = {
    "Chicago Bears": ["Ryan Poles", "Ben Johnson", "Caleb Williams",
                      "Dennis Allen", "Declan Doyle"],
    "Detroit Lions": ["Dan Campbell", "Brad Holmes", "Jared Goff",
                      "John Morton", "Kelvin Sheppard", "Aidan Hutchinson"],
    "Green Bay Packers": ["Matt LaFleur", "Brian Gutekunst", "Jordan Love",
                          "Jeff Hafley", "Adam Stenavich", "Josh Jacobs"],
    "Minnesota Vikings": ["Kevin O'Connell", "Kwesi Adofo-Mensah",
                          "J.J. McCarthy", "Brian Flores", "Justin Jefferson"],
}


def classify_media(title, team=None):
    """Return (kind, speaker). kind is 'presser' or 'clip'."""
    low = (title or "").lower()
    is_presser = any(m in low for m in PRESSER_MARKERS)

    speaker = ""
    candidates = SPEAKERS.get(team, []) if team else [
        n for names in SPEAKERS.values() for n in names]
    for name in candidates:
        if name.lower() in low:
            speaker = name
            break

    if not speaker and is_presser:
        # "Ryan Poles Press Conference | Chicago Bears" -> take the run of
        # capitalised words before the marker.
        m = re.match(r"^([A-Z][\w'\.-]+(?: [A-Z][\w'\.-]+){0,2})\b", title or "")
        if m and len(m.group(1).split()) >= 2:
            speaker = m.group(1)

    # A named coach or GM speaking is a presser even if the club titled it
    # something cute.
    if speaker and not is_presser:
        if any(w in low for w in ("says", "on ", "talks", "reacts", "explains")):
            is_presser = True

    return ("presser" if is_presser else "clip"), speaker


_ROSTER_CACHE = None


def relevance_keywords():
    """Static club terms plus every person harvested from the feeds."""
    global _ROSTER_CACHE
    if _ROSTER_CACHE is None:
        names = set()
        try:
            import roster
            names = roster.all_names()
        except Exception as e:
            print(f"   ⚠️  roster unavailable ({type(e).__name__}) — using core list only")
        _ROSTER_CACHE = set(STATIC_KEYWORDS) | set(CORE_PEOPLE) | names
    return _ROSTER_CACHE


def is_nfc_north_relevant(text):
    haystack = (text or "").lower()
    return any(keyword in haystack for keyword in relevance_keywords())


def entry_age_days(entry, now):
    if "published_parsed" in entry and entry.published_parsed:
        try:
            pub_datetime = datetime.fromtimestamp(mktime(entry.published_parsed))
            return (now - pub_datetime).days
        except Exception:
            return 0
    return 0


def fetch_all_sources():
    """Fetch every registered feed. Returns (by_team, health).

    by_team maps a club name to a list of (entry, source) pairs. League-wide
    wires are routed to whichever clubs a story actually mentions, and dropped
    if it mentions none -- otherwise the board fills with AFC news.

    A dead feed is logged and skipped. It never breaks the run, and it never
    silently narrows the board without saying so.
    """
    import sources
    from collections import defaultdict

    by_team = defaultdict(list)
    health = []

    for src in sources.active_sources():
        try:
            feed = feedparser.parse(src["url"])
            entries = list(feed.entries or [])
        except Exception as e:
            entries = []
            print(f"   ⚠️  {src['label']}: fetch failed ({type(e).__name__})")

        if not entries:
            health.append((src["label"], src["kind"], 0, "unreachable/empty"))
            if src["status"] == "verified":
                print(f"   ⚠️  {src['label']}: returned nothing (was verified)")
            continue

        routed = 0
        if src["team"] == "division":
            for e in entries:
                import re as _re2
                clean_summary = _re2.sub('<[^<]+?>', '', e.get("summary", "") or "")
                for team in sources.route_to_teams(e.get("title", ""), clean_summary):
                    by_team[team].append((e, src))
                    routed += 1
        else:
            team = src["team"]
            for e in entries:
                by_team[team].append((e, src))
                routed += 1

        health.append((src["label"], src["kind"], routed, "ok"))
        print(f"   ✅ {src['label']}: {routed} item(s)")

    return by_team, health


def get_top_team_news():
    import database
    import scoring

    print(" 🏈 Scraping division feeds...")
    by_team, health = fetch_all_sources()

    live = sum(1 for _, _, n, s in health if s == "ok")
    print(f" 📡 {live}/{len(health)} feeds returned content")

    # Learn who is on these rosters before anything is filtered by relevance,
    # so a player acquired today is recognised in today's national clips.
    try:
        import roster
        rosters = roster.harvest(by_team)
        roster.prune(rosters)
        roster.save_rosters(rosters)
        global _ROSTER_CACHE
        _ROSTER_CACHE = None          # force reload with the new names
        counts = roster.summary(rosters)
        print(f" 👥 Roster: " + ", ".join(f"{k.split()[-1]} {v}" for k, v in counts.items()))
    except Exception as e:
        print(f"   ⚠️  Roster harvest failed ({type(e).__name__}: {e})")

    # Build the scoring corpus once, across every source, so vocabulary rarity
    # and multi-day narrative momentum are measured over the whole division.
    scoring_corpus = []
    for team, pairs in by_team.items():
        for e, src in pairs:
            scoring_corpus.append({
                "title": e.get("title", ""),
                "summary": re.sub('<[^<]+?>', '', e.get("summary", "") or ""),
                "pub": e.get("published", ""),
                "team": team,
            })
    corpus_stats = scoring.build_corpus_stats(scoring_corpus)

    final_sorted_report = {}
    now = datetime.now()

    for team_name, pairs in by_team.items():
        scored_entries = []
        seen_links = set()

        for entry, src in pairs:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            if entry_age_days(entry, now) > MAX_AGE_DAYS:
                continue

            title = entry.get("title", "(No Title)")
            pub_date = entry.get("published", now.strftime("%Y-%m-%d %H:%M"))

            thumbnail = ""
            for l in (entry.get("links") or []):
                if "image" in (l.get("type") or "") or l.get("rel") == "enclosure":
                    thumbnail = l.get("href", "")
                    break
            if not thumbnail and entry.get("media_thumbnail"):
                try:
                    thumbnail = entry.media_thumbnail[0]["url"]
                except (KeyError, IndexError, TypeError):
                    pass

            raw_summary = entry.get("summary", "No summary text provided by source.")
            clean_summary = re.sub('<[^<]+?>', '', raw_summary).strip()
            # 180 chars cut transaction posts off mid-list, hiding exactly the
            # names a producer needs (who was cut, who was signed). The summary
            # sits behind an expander, so extra length costs nothing on screen.
            if len(clean_summary) > 1200:
                clean_summary = clean_summary[:1197] + "..."

            score, reasons = scoring.score_story(
                {"title": title, "summary": clean_summary,
                 "link": link, "pub": pub_date},
                corpus_stats, team_name, now,
            )

            # Team .com feeds are the club's PR arm. When a non-PR outlet is
            # carrying a story, that is itself editorially meaningful -- it is
            # the category of source that broke Josh Jacobs' exempt-list move,
            # which no club site would ever publish.
            if src["kind"] in ("wire", "paper", "blog"):
                score += 6.0
                reasons.append(f"independent source ({src['label']})")

            scored_entries.append(
                (score, title, clean_summary, link, pub_date, thumbnail,
                 "; ".join(reasons)))

        scored_entries.sort(key=lambda x: x[0], reverse=True)

        # Persist EVERY story inside the freshness window, each with its score.
        # Previously only the top 5 were saved, so anything ranked 6th or lower
        # was destroyed at scrape time and unrecoverable without a re-scrape.
        # Ranking now happens at read time in app.py, which makes the 5-story
        # cutoff a display choice rather than permanent data loss.
        for score, title, summary, link, pub_date, thumbnail, reason_text in scored_entries:
            database.save_team_news_with_media(
                team_name, title, summary, link, pub_date, thumbnail,
                score, reason_text
            )

        final_sorted_report[team_name] = scored_entries[:5]

    return final_sorted_report


def scrape_youtube_media_bites():
    import database
    import urllib.request

    print("🎥 Scraping YouTube feeds for NFC North content...")
    now = datetime.now()
    saved = 0
    presser_pressers = []   # (team, title, speaker, link, published)

    feed_jobs = []
    for label, url in NATIONAL_YOUTUBE_FEEDS.items():
        feed_jobs.append((label, url, False))
    for label, url in TEAM_YOUTUBE_FEEDS.items():
        feed_jobs.append((label, url, True))

    for label, url, is_team_channel in feed_jobs:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                feed_data = feedparser.parse(response.read())

            if not feed_data.entries:
                print(f"   ⚠️ Empty feed for {label}")
                continue

            kept = 0
            for entry in feed_data.entries[:15]:
                if entry_age_days(entry, now) > MAX_AGE_DAYS:
                    continue

                video_title = entry.get("title", "")
                video_link = entry.get("link", "")
                if not video_link:
                    continue

                # Team channels: keep recent clips. National shows: require NFC North keywords.
                if not is_team_channel and not is_nfc_north_relevant(video_title):
                    continue

                team_for_channel = CHANNEL_TEAMS.get(label)
                kind, speaker = classify_media(video_title, team_for_channel)

                if kind == "presser":
                    prefix = f"🎙️ {speaker}: " if speaker else "🎙️ Presser: "
                elif is_team_channel:
                    prefix = "🏈 Team: "
                else:
                    prefix = "🎥 Clip: "
                display_text = f"{prefix}{video_title}"

                if entry.get("published_parsed"):
                    published = datetime.fromtimestamp(mktime(entry.published_parsed)).strftime("%Y-%m-%d %H:%M")
                else:
                    published = now.strftime("%Y-%m-%d %H:%M")

                database.save_media_bite(label, display_text, video_link, published,
                                         platform="youtube", kind=kind, speaker=speaker)

                # A press conference is a story, not just a clip. Push it into
                # the team board too so it ranks against written coverage --
                # every "==" break in the rundown is a SOT.
                if kind == "presser" and team_for_channel:
                    presser_pressers.append(
                        (team_for_channel, video_title, speaker, video_link, published))

                kept += 1
                saved += 1
                if kept >= MAX_VIDEOS_PER_FEED:
                    break

            if kept:
                print(f"   ✅ {label}: saved {kept} relevant video(s)")
            else:
                print(f"   ⏭️ {label}: no NFC North hits inside {MAX_AGE_DAYS}-day window")

        except Exception as e:
            print(f"   ⚠️ YouTube check failed for {label}: {e}")

    # Press conferences also become team_news rows so they rank against written
    # coverage rather than sitting in a separate bucket the ranking never sees.
    if presser_pressers:
        import scoring
        corpus = [{"title": t, "summary": f"Press conference. {sp}".strip(),
                   "pub": p, "team": tm}
                  for tm, t, sp, _, p in presser_pressers]
        stats = scoring.build_corpus_stats(corpus)
        for team, title, speaker, link, published in presser_pressers:
            summary = (f"Press conference video"
                       + (f" — {speaker}." if speaker else ".")
                       + " Usable as a SOT.")
            score, reasons = scoring.score_story(
                {"title": title, "summary": summary, "link": link, "pub": published},
                stats, team, now)
            score += 12.0
            reasons.append("press conference (SOT available)")
            if speaker:
                reasons.append(f"speaker: {speaker}")
            database.save_team_news_with_media(
                team, f"🎙️ {title}", summary, link, published, "",
                score, "; ".join(reasons))
        print(f"   🎙️ {len(presser_pressers)} press conference(s) added to team boards")

    print(f"🎥 YouTube scrape complete — {saved} item(s) saved")
    return saved


def scrape_x_media_bites():
    """Disabled. See X_SCRAPING_DISABLED above.

    Kept as a no-op so any external caller or scheduled job that still
    references it fails safely and loudly rather than crashing.
    """
    print("🚫 X scraping is disabled (ToS + account suspension). Using Bluesky.")
    return 0


def scrape_bluesky_media_bites():
    """Pull division-relevant Bluesky posts. No auth, no browser."""
    import database

    try:
        import bluesky
    except ImportError:
        print("   ⚠️  bluesky.py missing — skipping social scrape")
        return 0

    print("🦋 Scraping Bluesky for NFC North posts...")
    try:
        posts = bluesky.collect(relevance_fn=is_nfc_north_relevant)
    except Exception as e:
        print(f"   ⚠️  Bluesky collect failed ({type(e).__name__}: {e})")
        return 0

    saved = 0
    for p in posts:
        try:
            database.save_media_bite(
                p["source"], p["text"], p["link"], p["fetched_at"],
                platform="bluesky", kind="clip", speaker=p.get("author_display", ""),
            )
            saved += 1
        except Exception:
            continue

    if saved:
        print(f"🦋 Bluesky scrape complete — {saved} post(s) saved")
    else:
        print("🦋 Bluesky returned nothing. Run `python check_bluesky.py` to "
              "confirm the API shape and handles.")
    return saved


def main():
    import database
    import sqlite3

    database.init_db()
    removed = database.clear_stale_media_bites(MAX_AGE_DAYS)
    if removed:
        print(f"🧹 Cleared {removed} stale media bite(s) older than {MAX_AGE_DAYS} days")

    # Remove old fake fallback rows from previous scraper versions
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM media_bites WHERE link = ? AND tweet_text LIKE ?",
        ("https://www.youtube.com", "Reviewing updated camp depth charts%"),
    )
    if cursor.rowcount:
        print(f"🧹 Removed {cursor.rowcount} placeholder fallback row(s)")
    conn.commit()
    conn.close()

    get_top_team_news()
    scrape_youtube_media_bites()
    scrape_bluesky_media_bites()
