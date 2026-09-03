import os
import sqlite3
from datetime import datetime, timedelta

# Absolute, so the DB can never depend on the directory Streamlit was launched
# from. A relative path silently creates a second, empty database when the
# working directory differs from the app directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "northscout.db")

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
            thumbnail TEXT,
            score REAL DEFAULT 0,
            reasons TEXT DEFAULT ''
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
    
    # Column migrations. "duplicate column name" is expected and benign; any
    # other OperationalError is a real failure and must not be swallowed.
    for table, coldef in (
        ("team_news", "thumbnail TEXT DEFAULT ''"),
        ("team_news", "score REAL DEFAULT 0"),
        ("team_news", "reasons TEXT DEFAULT ''"),
        ("media_bites", "platform TEXT DEFAULT 'youtube'"),
    ):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {coldef};")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                print(f"MIGRATION FAILED on {table}.{coldef.split()[0]}: {e}")
        
    conn.commit()
    conn.close()

def save_team_news_with_media(team, title, summary, link, fetched_at, thumbnail,
                              score=0, reasons=""):
    """Store a story, keyed on LINK rather than title.

    NFL clubs recycle a single headline for every transaction -- the Bears feed
    routinely carries eight separate stories all titled "Chicago Bears announce
    roster moves". Deduping on title meant only the first was ever kept, and
    every later cut, signing and trade was silently discarded as a duplicate.
    The link is the only stable unique identifier these feeds provide.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM team_news WHERE link = ?", (link,))
    row = cursor.fetchone()
    if row:
        # Already known: refresh score and reasons so re-ranking reflects this run.
        cursor.execute("UPDATE team_news SET score = ?, reasons = ? WHERE id = ?",
                       (score, reasons, row[0]))
    else:
        cursor.execute("""
            INSERT INTO team_news
                (team, title, summary, link, fetched_at, thumbnail, score, reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (team, title, summary, link, fetched_at, thumbnail, score, reasons))
    conn.commit()
    conn.close()

def save_team_news(team, title, summary, link, fetched_at):
    save_team_news_with_media(team, title, summary, link, fetched_at, "", 0, "")

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
