import feedparser
import re
import os
import random
import time
from collections import Counter
from datetime import datetime
from time import mktime

TEAMS = {
    "Chicago Bears": "https://www.chicagobears.com/rss/news",
    "Detroit Lions": "https://www.detroitlions.com/rss/news",
    "Green Bay Packers": "https://www.packers.com/rss/news",
    "Minnesota Vikings": "https://www.vikings.com/rss/news",
    "Sports Mockery (Bears/NFC)": "https://sportsmockery.com/category/bears/feed",
}

IGNORE_WORDS = {"the", "a", "and", "in", "to", "for", "of", "on", "with", "at", "is", "nfc", "north", "teams", "this", "that", "from"}

NFC_KEYWORDS = [
    "bears", "lions", "packers", "vikings", "nfc north", "nfcnorth",
    "chicago", "detroit", "green bay", "minnesota", "halas", "lambeau",
    "soldier field", "ford field", "u.s. bank", "us bank stadium",
    "caleb williams", "aidan hutchinson", "jordan love", "j.j. mccarthy",
    "jj mccarthy", "kyler murray", "ben johnson", "dan campbell",
    "matt lafleur", "kevin o'connell", "kevin oconnell",
]

# National / show channels need keyword hits. Team channels are inherently relevant.
NATIONAL_YOUTUBE_FEEDS = {
    "@PatMcAfeeShow": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
    "@TheHerd": "https://www.youtube.com/feeds/videos.xml?channel_id=UCFDidMd82mpDkKijLUqHp7A",
    "@SportsCenter": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiWLfSweyRNmLpgEHekhoAg",
}

TEAM_YOUTUBE_FEEDS = {
    "Chicago Bears YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP0Cdc6moLMyDJiO0s-yhbQ",
    "Detroit Lions YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCv5J06V-ESk5_1uriG65f3w",
    "Green Bay Packers YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJtI-l6La0zniodFtSHYrBg",
    "Minnesota Vikings YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcsw_KrB_wg5lQ5nXWR_LFA",
}

X_ACCOUNTS = [
    # Official team accounts
    ("X @ChicagoBears", "ChicagoBears", True),
    ("X @Lions", "Lions", True),
    ("X @packers", "packers", True),
    ("X @Vikings", "Vikings", True),
    # Beat / division voices
    ("X @BradBiggs", "BradBiggs", False),
    ("X @AdamHoge", "AdamHoge", False),
    ("X @justinrridge", "justinrridge", False),
    ("X @robdemovsky", "robdemovsky", False),
    ("X @Kevin_Seifert", "Kevin_Seifert", False),
]

MAX_AGE_DAYS = 8
MAX_VIDEOS_PER_FEED = 5
MAX_TWEETS_PER_ACCOUNT = 3


def calculate_global_trends(all_entries):
    words = []
    for entry in all_entries:
        title = entry.get("title", "").lower()
        clean_words = re.findall(r'\b\w+\b', title)
        keywords = [w for w in clean_words if w not in IGNORE_WORDS and not w.isdigit() and len(w) > 2]
        words.extend(keywords)
    return Counter(words)


def is_nfc_north_relevant(text):
    haystack = (text or "").lower()
    return any(keyword in haystack for keyword in NFC_KEYWORDS)


def entry_age_days(entry, now):
    if "published_parsed" in entry and entry.published_parsed:
        try:
            pub_datetime = datetime.fromtimestamp(mktime(entry.published_parsed))
            return (now - pub_datetime).days
        except Exception:
            return 0
    return 0


def get_top_team_news():
    import database
    all_raw_entries = []
    team_feeds = {}

    print(" 🏈 Scraping division feeds...")
    for team_name, url in TEAMS.items():
        feed = feedparser.parse(url)
        if not feed.bozo or feed.entries:
            team_feeds[team_name] = feed.entries
            all_raw_entries.extend(feed.entries)

    trending_keywords = calculate_global_trends(all_raw_entries)
    final_sorted_report = {}
    now = datetime.now()

    for team_name, entries in team_feeds.items():
        display_name = "Chicago Bears" if "Sports Mockery" in team_name else team_name
        scored_entries = []

        for entry in entries:
            is_recent = True
            if "published_parsed" in entry and entry.published_parsed:
                try:
                    pub_datetime = datetime.fromtimestamp(mktime(entry.published_parsed))
                    age_days = (now - pub_datetime).days
                    if age_days > MAX_AGE_DAYS:
                        is_recent = False
                except Exception:
                    pass

            if not is_recent:
                continue

            title = entry.get("title", "(No Title)")
            link = entry.get("link", "#")
            pub_date = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M"))

            thumbnail = "https://www.chicagobears.com/assets/images/featured/bears-default.jpg"
            if "links" in entry:
                for l in entry.links:
                    if "image" in l.get("type", "") or l.get("rel") == "enclosure":
                        thumbnail = l.get("href")
                        break

            if thumbnail.endswith("bears-default.jpg") and "media_thumbnail" in entry:
                thumbnail = entry.media_thumbnail[0]["url"]

            raw_summary = entry.get("summary", "No summary text provided by source.")
            clean_summary = re.sub('<[^<]+?>', '', raw_summary).strip()
            # 180 chars cut transaction posts off mid-list, hiding exactly the
            # names a producer needs (who was cut, who was signed). The summary
            # sits behind an expander, so extra length costs nothing on screen.
            if len(clean_summary) > 1200:
                clean_summary = clean_summary[:1197] + "..."

            score = 0
            title_lower = title.lower()
            for word in trending_keywords:
                if word in title_lower:
                    score += trending_keywords[word]

            scored_entries.append((score, title, clean_summary, link, pub_date, thumbnail))

        scored_entries.sort(key=lambda x: x[0], reverse=True)

        # Persist EVERY story inside the freshness window, each with its score.
        # Previously only the top 5 were saved, so anything ranked 6th or lower
        # was destroyed at scrape time and unrecoverable without a re-scrape.
        # Ranking now happens at read time in app.py, which makes the 5-story
        # cutoff a display choice rather than permanent data loss.
        for score, title, summary, link, pub_date, thumbnail in scored_entries:
            database.save_team_news_with_media(
                display_name, title, summary, link, pub_date, thumbnail, score
            )

        top_five = scored_entries[:5]
        if display_name in final_sorted_report:
            combined = final_sorted_report[display_name] + top_five
            combined.sort(key=lambda x: x[0], reverse=True)
            final_sorted_report[display_name] = combined[:5]
        else:
            final_sorted_report[display_name] = top_five

    return final_sorted_report


def scrape_youtube_media_bites():
    import database
    import urllib.request

    print("🎥 Scraping YouTube feeds for NFC North content...")
    now = datetime.now()
    saved = 0

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

                prefix = "🏈 Team: " if is_team_channel else "🎥 Clip: "
                display_text = f"{prefix}{video_title}"
                if entry.get("published_parsed"):
                    published = datetime.fromtimestamp(mktime(entry.published_parsed)).strftime("%Y-%m-%d %H:%M")
                else:
                    published = now.strftime("%Y-%m-%d %H:%M")
                database.save_media_bite(label, display_text, video_link, published, platform="youtube")
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

    print(f"🎥 YouTube scrape complete — {saved} item(s) saved")
    return saved


def scrape_x_media_bites():
    """Pull recent posts from allowlisted X accounts via Playwright + saved session cookies."""
    import database
    import json

    print("🐦 Scraping X/Twitter for NFC North posts...")
    auth_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twitter_auth.json")
    if not os.path.exists(auth_path):
        print("   ⚠️ twitter_auth.json not found — skipping X scrape")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   ⚠️ playwright not installed — skipping X scrape (pip install playwright)")
        return 0

    with open(auth_path, "r", encoding="utf-8") as f:
        storage_state = json.load(f)

    now = datetime.now()
    saved = 0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=storage_state,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            for label, handle, is_team_account in X_ACCOUNTS:
                try:
                    page.goto(
                        f"https://x.com/{handle}",
                        wait_until="domcontentloaded",
                        timeout=25000,
                    )
                    page.wait_for_timeout(3500)

                    body_text = (page.inner_text("body") or "")[:500].lower()
                    if "sign in to x" in body_text or "log in to x" in body_text:
                        print(f"   ⚠️ X session may be expired (login wall on @{handle})")
                        break

                    articles = page.query_selector_all('article[data-testid="tweet"]')
                    kept = 0
                    for article in articles:
                        if kept >= MAX_TWEETS_PER_ACCOUNT:
                            break
                        try:
                            text_el = article.query_selector('div[data-testid="tweetText"]')
                            tweet_text = text_el.inner_text().strip() if text_el else ""
                            if not tweet_text:
                                continue

                            if not is_team_account and not is_nfc_north_relevant(tweet_text):
                                continue

                            link_el = article.query_selector('a[href*="/status/"]')
                            href = link_el.get_attribute("href") if link_el else None
                            if not href:
                                continue
                            if href.startswith("/"):
                                href = f"https://x.com{href}"

                            time_el = article.query_selector("time")
                            fetched_time = now.strftime("%Y-%m-%d %H:%M")
                            if time_el:
                                dt_attr = time_el.get_attribute("datetime")
                                if dt_attr:
                                    try:
                                        post_dt = datetime.fromisoformat(
                                            dt_attr.replace("Z", "+00:00")
                                        ).replace(tzinfo=None)
                                        if (now - post_dt).days > MAX_AGE_DAYS:
                                            continue
                                        fetched_time = post_dt.strftime("%Y-%m-%d %H:%M")
                                    except ValueError:
                                        pass

                            database.save_media_bite(
                                label,
                                tweet_text[:280],
                                href.split("?")[0],
                                fetched_time,
                                platform="x",
                            )
                            kept += 1
                            saved += 1
                        except Exception:
                            continue

                    if kept:
                        print(f"   ✅ @{handle}: saved {kept} post(s)")
                    else:
                        print(f"   ⏭️ @{handle}: no matching posts found")

                    time.sleep(random.uniform(1.2, 2.4))

                except Exception as e:
                    print(f"   ⚠️ X scrape failed for @{handle}: {e}")
                    continue

            browser.close()
    except Exception as e:
        print(f"   ⚠️ Playwright X scrape aborted: {e}")
        return saved

    print(f"🐦 X scrape complete — {saved} post(s) saved")
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
    scrape_x_media_bites()
