import feedparser
import re
from collections import Counter
from datetime import datetime

TEAMS = {
    "Chicago Bears": "https://www.chicagobears.com/rss/news",
    "Detroit Lions": "https://www.detroitlions.com/rss/news",
    "Green Bay Packers": "https://www.packers.com/rss/news",
    "Minnesota Vikings": "https://www.vikings.com/rss/news",
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
    
    print("🏈 Scraping division feeds...")
    for team_name, url in TEAMS.items():
        feed = feedparser.parse(url)
        if not feed.bozo or feed.entries:
            team_feeds[team_name] = feed.entries
            all_raw_entries.extend(feed.entries)
            
    trending_keywords = calculate_global_trends(all_raw_entries)
    final_sorted_report = {}
    
    # Structural Markdown generation for your local desktop failsafe file
    markdown_backup = f"# 🏈 NORTHSCOUT FAILSAFE SHOW PREP REPORT\n"
    markdown_backup += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for team_name, entries in team_feeds.items():
        scored_entries = []
        for entry in entries:
            title = entry.get("title", "(No Title)")
            link = entry.get("link", "#")
            
            score = 0
            title_lower = title.lower()
            for word in trending_keywords:
                if word in title_lower:
                    score += trending_keywords[word]
            
            scored_entries.append((score, title, link))
        
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        top_five = scored_entries[:5]
        final_sorted_report[team_name] = top_five
        
        # Build out the text backup data block
        markdown_backup += f"## {team_name} (Top Trending)\n"
        for idx, (score, title, link) in enumerate(top_five, 1):
            markdown_backup += f"{idx}. {title}\n   Source: {link}\n"
            database.save_team_news(team_name, title, link)
        markdown_backup += "\n"
        
    # Write the bulletproof failsafe file down to your folder
    with open("show_prep.md", "w", encoding="utf-8") as f:
        f.write(markdown_backup)
        
    return final_sorted_report

def main():
    report = get_top_team_news()
    print("\n🎉 SUCCESS! Popularity metrics processed. Local failsafe 'show_prep.md' updated!")

if __name__ == "__main__":
    main()