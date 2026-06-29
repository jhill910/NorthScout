import sqlite3
from datetime import datetime

DB_NAME = "northscout.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT,
            title TEXT,
            summary TEXT,
            link TEXT,
            fetched_at TEXT,
            thumbnail TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_bites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            tweet_text TEXT,
            link TEXT,
            fetched_at TEXT
        )
    """)
    
    # Structural updates to prevent backward errors with older local file versions
    try:
        cursor.execute("ALTER TABLE team_news ADD COLUMN thumbnail TEXT;")
    except sqlite3.OperationalError:
        pass # Already upgraded
        
    conn.commit()
    conn.close()

def save_team_news_with_media(team, title, summary, link, fetched_at, thumbnail):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM team_news WHERE team = ? AND title = ?", (team, title))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO team_news (team, title, summary, link, fetched_at, thumbnail)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (team, title, summary, link, fetched_at, thumbnail))
        conn.commit()
    conn.close()

def save_team_news(team, title, summary, link, fetched_at):
    save_team_news_with_media(team, title, summary, link, fetched_at, "")

def save_media_bite(source, tweet_text, link, fetched_at):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM media_bites WHERE source = ? AND tweet_text = ?", (source, tweet_text))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO media_bites (source, tweet_text, link, fetched_at)
            VALUES (?, ?, ?, ?)
        """, (source, tweet_text, link, fetched_at))
        conn.commit()
    conn.close()