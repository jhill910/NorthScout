import sqlite3

def init_db():
    conn = sqlite3.connect("northscout.db")
    cursor = conn.cursor()
    
    # 1. Team News Table (RSS Trends with summary field)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT,
            title TEXT UNIQUE,
            summary TEXT,
            link TEXT,
            fetched_at TEXT
        )
    """)
    
    # 2. Media Bites Table (Playwright Tweets with tweet_text field)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_bites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            tweet_text TEXT,
            link TEXT UNIQUE,
            fetched_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_team_news(team, title, summary, link, actual_pub_time):
    conn = sqlite3.connect("northscout.db")
    cursor = conn.cursor()
    # Stores the actual feed-provided publication timestamp
    cursor.execute("""
        INSERT OR IGNORE INTO team_news (team, title, summary, link, fetched_at)
        VALUES (?, ?, ?, ?, ?)
    """, (team, title, summary, link, actual_pub_time))
    conn.commit()
    conn.close()

def save_media_bite(source, tweet_text, link, actual_tweet_time):
    conn = sqlite3.connect("northscout.db")
    cursor = conn.cursor()
    # Explicitly naming the 4 target columns fixes the mismatch!
    cursor.execute("""
        INSERT OR IGNORE INTO media_bites (source, tweet_text, link, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (source, tweet_text, link, actual_tweet_time))
    conn.commit()
    conn.close()