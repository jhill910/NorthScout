import sqlite3
from datetime import datetime, timedelta

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
            fetched_at TEXT,
            platform TEXT DEFAULT 'youtube'
        )
    """)
    
    try:
        cursor.execute("ALTER TABLE team_news ADD COLUMN thumbnail TEXT DEFAULT '';")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE media_bites ADD COLUMN platform TEXT DEFAULT 'youtube';")
    except sqlite3.OperationalError:
        pass
        
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

def save_media_bite(source, tweet_text, link, fetched_at, platform="youtube"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM media_bites WHERE link = ? OR (source = ? AND tweet_text = ?)",
        (link, source, tweet_text),
    )
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO media_bites (source, tweet_text, link, fetched_at, platform)
            VALUES (?, ?, ?, ?, ?)
        """, (source, tweet_text, link, fetched_at, platform))
        conn.commit()
    conn.close()

def clear_stale_media_bites(max_age_days=8):
    """Remove media rows older than max_age_days based on fetched_at timestamp."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fetched_at FROM media_bites")
    cutoff = datetime.now() - timedelta(days=max_age_days)
    stale_ids = []
    for row_id, fetched_at in cursor.fetchall():
        parsed = _parse_media_timestamp(fetched_at)
        if parsed and parsed < cutoff:
            stale_ids.append(row_id)
    if stale_ids:
        cursor.executemany("DELETE FROM media_bites WHERE id = ?", [(i,) for i in stale_ids])
        conn.commit()
    conn.close()
    return len(stale_ids)


def _parse_media_timestamp(raw):
    if not raw:
        return None
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt, width in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        try:
            return datetime.strptime(text[:width], fmt)
        except ValueError:
            continue
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(text).replace(tzinfo=None)
    except Exception:
        return None
