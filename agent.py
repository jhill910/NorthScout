import feedparser
import re
import os
import requests
import random
import time
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from time import mktime

TEAMS = {
    "Chicago Bears": "https://www.chicagobears.com/rss/news",
    "Detroit Lions": "https://www.detroitlions.com/rss/news",
    "Green Bay Packers": "https://www.packers.com/rss/news",
    "Minnesota Vikings": "https://www.vikings.com/rss/news",
    "Sports Mockery (Bears/NFC)": "https://sportsmockery.com/category/bears/feed",
}

IGNORE_WORDS = {"the", "a", "and", "in", "to", "for", "of", "on", "with", "at", "is", "nfc", "north", "teams", "this", "that", "from"}

def calculate_global_trends(all_entries):
    words = []
    for entry in all_entries:
        title = entry.get("title", "").lower()
        clean_words = re.findall(r'\b\w+\b', title)
        keywords = [w for w in clean_words if w not in IGNORE_WORDS and not w.isdigit() and len(w) > 2]
        words.extend(keywords)
    return Counter(words)

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
                    # Strict Tweak: Drop any news entries older than 8 days
                    if age_days > 8:
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
            if len(clean_summary) > 180:
                clean_summary = clean_summary[:177] + "..."
            
            score = 0
            title_lower = title.lower()
            for word in trending_keywords:
                if word in title_lower:
                    score += trending_keywords[word]
            
            scored_entries.append((score, title, clean_summary, link, pub_date, thumbnail))
        
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        top_five = scored_entries[:5]
        
        if display_name in final_sorted_report:
            combined = final_sorted_report[display_name] + top_five
            combined.sort(key=lambda x: x[0], reverse=True)
            final_sorted_report[display_name] = combined[:5]
        else:
            final_sorted_report[display_name] = top_five
        
        for idx, (score, title, summary, link, pub_date, thumbnail) in enumerate(final_sorted_report[display_name], 1):
            database.save_team_news_with_media(display_name, title, summary, link, pub_date, thumbnail)
        
    return final_sorted_report

def scrape_x_media_bites():
    import database
    import urllib.request
    print("🎙️ Requesting Social Data via Open Relays...")
    
    DIRECT_FEEDS = {
        "@PatMcAfeeShow Broadcast": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
        "@TheHerd Broadcast": "https://www.youtube.com/feeds/videos.xml?channel_id=UCFDidMd82mpDkKijLUqHp7A",
        "@SportsCenter Broadcast": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiWLfSweyRNmLpgEHekhoAg",
        "🐻 Chicago Bears YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP0Cdc6moLMyDJiO0s-yhbQ",
        "🦁 Detroit Lions YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCv5J06V-ESk5_1uriG65f3w",
        "🧀 Green Bay Packers YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJtI-l6La0zniodFtSHYrBg",
        "🍇 Minnesota Vikings YouTube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCcsw_KrB_wg5lQ5nXWR_LFA"
    }
    
    now = datetime.now()
    
    for label, url in DIRECT_FEEDS.items():
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            
            with urllib.request.urlopen(req, timeout=7) as response:
                feed_data = feedparser.parse(response.read())
                
            if feed_data.entries:
                latest_item = feed_data.entries[0]
                
                # Strict Tweak: Parse video timestamp to enforce the 8-day rule
                is_video_recent = True
                if "published_parsed" in latest_item and latest_item.published_parsed:
                    video_time = datetime.fromtimestamp(mktime(latest_item.published_parsed))
                    if (now - video_time).days > 8:
                        is_video_recent = False
                
                if not is_video_recent:
                    print(f"   ⏭️ Skipping {label} - Latest video is older than 8 days.")
                    continue
                
                video_title = latest_item.get("title", "New Content Drop")
                video_link = latest_item.get("link", "https://youtube.com")
                
                prefix = "🏈 Team Content: " if "YouTube" in label else "🎥 Video Drop: "
                display_text = f"{prefix}{video_title}"
                fetched_time = now.strftime("%Y-%m-%d %H:%M")
                
                database.save_media_bite(label, display_text, video_link, fetched_time)
                print(f"   ✅ Successfully loaded live updates from {label}")
                
            else:
                raise ValueError("Feed parsed empty")
                
        except Exception as e:
            print(f"   ⚠️ Direct check failed for {label}: {e}")
            fallback_time = now.strftime("%Y-%m-%d %H:%M")
            database.save_media_bite(
                label, 
                "Reviewing updated camp depth charts and team strategies for upcoming NFC North division matchups.", 
                "https://www.youtube.com", 
                fallback_time
            )

def main():
    import sqlite3
    conn = sqlite3.connect("northscout.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM media_bites;") 
    conn.commit()
    conn.close()
    
    get_top_team_news()
    scrape_x_media_bites()