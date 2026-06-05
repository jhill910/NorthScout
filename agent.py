import feedparser
import re
import os
import sqlite3
from collections import Counter
from datetime import datetime
from playwright.sync_api import sync_playwright

TEAMS = {
    "Chicago Bears": "https://www.chicagobears.com/rss/news",
    "Detroit Lions": "https://www.detroitlions.com/rss/news",
    "Green Bay Packers": "https://www.packers.com/rss/news",
    "Minnesota Vikings": "https://www.vikings.com/rss/news",
}

TWITTER_HANDLES = ["PatMcAfeeShow", "adamschefter", "3andout_pod", "ZarkTweets", "TheHerd", "SportsCenter"]
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
    
    print("🏈 Scraping division feeds...")
    for team_name, url in TEAMS.items():
        feed = feedparser.parse(url)
        if not feed.bozo or feed.entries:
            team_feeds[team_name] = feed.entries
            all_raw_entries.extend(feed.entries)
            
    trending_keywords = calculate_global_trends(all_raw_entries)
    final_sorted_report = {}
    
    for team_name, entries in team_feeds.items():
        scored_entries = []
        for entry in entries:
            title = entry.get("title", "(No Title)")
            link = entry.get("link", "#")
            
            # UPDATED: Capture the actual original publication date from the RSS feed item
            pub_date = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M"))
            # Clean up long messy timezones if present for a tighter UI fit
            pub_date = pub_date.replace(" +0000", "").replace(" GMT", "")
            
            raw_summary = entry.get("summary", "No summary text provided by source.")
            clean_summary = re.sub('<[^<]+?>', '', raw_summary).strip()
            if len(clean_summary) > 180:
                clean_summary = clean_summary[:177] + "..."
            
            score = 0
            title_lower = title.lower()
            for word in trending_keywords:
                if word in title_lower:
                    score += trending_keywords[word]
            
            scored_entries.append((score, title, clean_summary, link, pub_date))
        
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        top_five = scored_entries[:5]
        final_sorted_report[team_name] = top_five
        
        for idx, (score, title, summary, link, pub_date) in enumerate(top_five, 1):
            # Save using the actual published timestamp
            database.save_team_news(team_name, title, summary, link, pub_date)
        
    return final_sorted_report

def scrape_x_media_bites():
    import database
    import json
    import streamlit as st
    
    auth_file = "twitter_auth.json"
    
    # Check if we are running in the cloud, if so, write our secret string to a temporary file
    if not os.path.exists(auth_file) and "secret_auth" in st.secrets:
        with open(auth_file, "w") as f:
            f.write(st.secrets["secret_auth"]["json_data"])

    if not os.path.exists(auth_file):
        print("   ❌ Missing twitter authorization tokens.")
        return

    print("🎙️ Starting Playwright RPA Browser...")
    with sync_playwright() as p:
        # Force Playwright to use the cloud server's global Linux Chromium execution path
browser = p.chromium.launch(
    headless=True,
    executable_path="/usr/bin/chromium"
)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()
        
        for handle in TWITTER_HANDLES:
            try:
                page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                tweet_locator = page.locator('article[data-testid="tweet"]').first
                
                if tweet_locator.count() > 0:
                    text_element = tweet_locator.locator('div[data-testid="tweetText"]').first
                    tweet_text = text_element.inner_text() if text_element.count() > 0 else "Media content link."
                    
                    link_element = tweet_locator.locator('a[href*="/status/"]').first
                    if link_element.count() > 0:
                        href_attr = link_element.get_attribute("href")
                        tweet_url = f"https://x.com{href_attr}" if href_attr.startswith("/") else href_attr
                    else:
                        tweet_url = f"https://x.com/{handle}"
                    
                    # UPDATED: Pull the exact posted timestamp from X's native <time> attribute
                    time_element = tweet_locator.locator('time').first
                    if time_element.count() > 0:
                        raw_time = time_element.get_attribute("datetime") # Format: 2026-06-02T18:30:00.000Z
                        # Tidy it up cleanly into a readable format for show notes
                        tweet_time = raw_time.replace("T", " ").split(".")[0] + " UTC"
                    else:
                        tweet_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    tweet_text = tweet_text.replace("\n", " ")
                    database.save_media_bite(f"@{handle} Live", tweet_text, tweet_url, tweet_time)
            except Exception as e:
                print(f"   ❌ Error on @{handle}: {e}")
        context.close()
        browser.close()

def main():
    get_top_team_news()
    scrape_x_media_bites()

if __name__ == "__main__":
    main()