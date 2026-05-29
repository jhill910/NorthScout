import sqlite3
from datetime import datetime

DB_NAME = "northscout.db"

def init_db():
    """Initializes the database tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for Team News
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT,
            title TEXT UNIQUE,
            link TEXT,
            fetched_at TEXT
        )
    ''')
    
    # Table for Media Bites
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media_bites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT UNIQUE,
            link TEXT,
            fetched_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def save_team_news(team, title, link):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO team_news (team, title, link, fetched_at) VALUES (?, ?, ?, ?)",
            (team, title, link, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()
    except Exception as e:
        pass
    conn.close()

def save_media_bite(source, title, link):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO media_bites (source, title, link, fetched_at) VALUES (?, ?, ?, ?)",
            (source, title, link, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()
    except Exception as e:
        pass
    conn.close()