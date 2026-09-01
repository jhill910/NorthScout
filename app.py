import sys
import os
# Force Python to read the absolute folder directory path before anything else runs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import sqlite3
import pandas as pd
import time
from datetime import datetime, timezone

# Initialize database
import database
database.init_db()

# --- CONFIG & APP WORKSPACE SETUP ---
st.set_page_config(page_title="NorthScout Dashboard", page_icon="🏈", layout="wide")

# --- COUNTDOWN MATH FOR KICKOFF 2026 ---
def get_countdown_to_kickoff():
    # The 2026 NFL Regular Season kicks off Thursday night, September 10, 2026!
    kickoff_time = datetime(2026, 9, 10, 20, 35, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    time_delta = kickoff_time - now
    
    if time_delta.days < 0:
        return "🏈 THE 2026 SEASON IS LIVE"
    
    days = time_delta.days
    hours = time_delta.seconds // 3600
    minutes = (time_delta.seconds % 3600) // 60
    return f"⏱️ {days}d : {hours}h : {minutes}m until 2026 Regular Season Kickoff"

# --- DATABASE LOADING ENGINES ---
def load_dashboard_data(team_name):
    conn = sqlite3.connect("northscout.db")
    query = "SELECT title, summary, link, fetched_at, thumbnail FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5"
    df = pd.read_sql_query(query, conn, params=(team_name,))
    conn.close()
    return df

def load_media_data(platform=None, limit=8):
    conn = sqlite3.connect("northscout.db")
    query = """
        SELECT source, tweet_text, link, fetched_at, COALESCE(platform, '') AS platform
        FROM media_bites
        ORDER BY id DESC
        LIMIT 80
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return df

    def infer_platform(row):
        tagged = str(row.get("platform") or "").strip().lower()
        if tagged in ("youtube", "x"):
            return tagged
        link = str(row.get("link") or "").lower()
        if "youtube.com" in link or "youtu.be" in link:
            return "youtube"
        if "x.com" in link or "twitter.com" in link:
            return "x"
        return ""

    df["_platform"] = df.apply(infer_platform, axis=1)
    if platform:
        df = df[df["_platform"] == platform]
    return df.drop(columns=["_platform"]).head(limit).reset_index(drop=True)

def render_media_cards(media_df, empty_message):
    if media_df.empty:
        st.info(empty_message)
        return

    sub_cols = st.columns(4)
    for idx, row in media_df.iterrows():
        col_target = idx % 4
        with sub_cols[col_target]:
            with st.container(border=True):
                st.markdown(f"##### 📢 {row['source']}")
                st.caption(f"🕒 {row['fetched_at']}")

                post_text = row['tweet_text'] if row['tweet_text'] else "[No text content captured]"
                st.markdown(
                    f"""
                    <div style="height: 110px; margin-top: 10px; margin-bottom: 10px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;">
                        <a href="{row['link']}" target="_blank" style="text-decoration: none; color: #000000; font-style: italic; font-size: 14px; line-height: 1.4;">
                            "{post_text}"
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# --- FIXED LOGO ASSETS & PROMINENT TEAM COLOR PALETTES ---
TEAM_ASSETS = {
    "Chicago Bears": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png",
        "bg_color": "#0B162A", "text_color": "#E64303", "glow": "rgba(230, 67, 3, 0.3)"
    },
    "Detroit Lions": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
        "bg_color": "#0076B6", "text_color": "#B0B7BC", "glow": "rgba(0, 118, 182, 0.3)"
    },
    "Green Bay Packers": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
        "bg_color": "#203731", "text_color": "#FFB612", "glow": "rgba(255, 182, 18, 0.3)"
    },
    "Minnesota Vikings": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
        "bg_color": "#4F2683", "text_color": "#FFC62F", "glow": "rgba(79, 38, 131, 0.3)"
    }
}

# --- GLOBAL CSS TAB ACCENT HIGHLIGHT PATCH ---
st.markdown(
    """
    <style>
        button[id*="tab"] { background-color: #11141a !important; color: #8b949e !important; transition: all 0.25s ease-in-out; font-size: 15px !important; }
        button[id*="tab-0"][aria-selected="true"] { border-bottom: 4px solid #E64303 !important; color: white !important; background-color: #0B162A !important; font-weight: bold !important; }
        button[id*="tab-1"][aria-selected="true"] { border-bottom: 4px solid #B0B7BC !important; color: white !important; background-color: #0076B6 !important; font-weight: bold !important; }
        button[id*="tab-2"][aria-selected="true"] { border-bottom: 4px solid #FFB612 !important; color: white !important; background-color: #203731 !important; font-weight: bold !important; }
        button[id*="tab-3"][aria-selected="true"] { border-bottom: 4px solid #FFC62F !important; color: white !important; background-color: #4F2683 !important; font-weight: bold !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# --- TOP BROADCAST REFRESH TICKER ---
st.markdown(
    f"""
    <div style="background: #11141a; padding: 18px; border-radius: 10px; border-bottom: 4px solid #E64303; text-align: center; margin-bottom: 25px;">
        <h2 style="margin: 0; color: #ffffff; font-family: 'Courier New', monospace; letter-spacing: 3px; font-weight: bold;">{get_countdown_to_kickoff()}</h2>
        <p style="margin: 6px 0 0 0; color: #8b949e; font-size: 13px; font-family: sans-serif; letter-spacing: 1px;">NORTHSCOUT CHICAGO PRODUCER DESK</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🏈 NorthScout: Master Show Prep App")
st.subheader(f"Snapshot Room — Week of {datetime.now().strftime('%B %d, %Y')}")
st.markdown("---")

# --- PRODUCER FOCUS PRIORITIZATION: DIVISION STANDINGS CONTAINER ---
st.markdown("### 📊 DIVISION STANDINGS (Bears-Centric Anchor Frame)")
st.markdown(
    """
    <div style="background-color: #0B162A; padding: 20px; border-radius: 12px; border-left: 8px solid #E64303; box-shadow: 0 4px 15px rgba(0,0,0,0.4); margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div style="text-align: center; min-width: 150px; border-right: 2px solid #1f2d42; padding-right: 10px;">
                <h5 style="color: #8b949e; margin: 0; font-size: 12px; letter-spacing: 1px;">🐻 CHI BEARS</h5>
                <h2 style="color: #E64303; margin: 5px 0 0 0; font-size: 26px; font-weight: bold;">11-6-0</h2>
                <span style="color: #238636; font-size: 12px; font-weight: bold;">+26 Diff</span>
            </div>
            <div style="text-align: center; min-width: 150px; border-right: 2px solid #1f2d42; padding-right: 10px;">
                <h5 style="color: #8b949e; margin: 0; font-size: 12px; letter-spacing: 1px;">🧀 GB PACKERS</h5>
                <h2 style="color: #FFB612; margin: 5px 0 0 0; font-size: 24px; font-weight: bold;">9-7-1</h2>
                <span style="color: #238636; font-size: 12px; font-weight: bold;">+31 Diff</span>
            </div>
            <div style="text-align: center; min-width: 150px; border-right: 2px solid #1f2d42; padding-right: 10px;">
                <h5 style="color: #8b949e; margin: 0; font-size: 12px; letter-spacing: 1px;">🍇 MIN VIKINGS</h5>
                <h2 style="color: #FFC62F; margin: 5px 0 0 0; font-size: 24px; font-weight: bold;">9-8-0</h2>
                <span style="color: #238636; font-size: 12px; font-weight: bold;">+11 Diff</span>
            </div>
            <div style="text-align: center; min-width: 150px;">
                <h5 style="color: #8b949e; margin: 0; font-size: 12px; letter-spacing: 1px;">🦁 DET LIONS</h5>
                <h2 style="color: #B0B7BC; margin: 5px 0 0 0; font-size: 24px; font-weight: bold;">9-8-0</h2>
                <span style="color: #238636; font-size: 12px; font-weight: bold;">+68 Diff</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <div style="background-color: #11141a; padding: 12px; border-radius: 6px; border: 1px solid #2d333b; margin-bottom: 25px;">
        <p style="margin: 0; font-size: 12px; color: #8b949e; line-height: 1.4;">
            💡 <b>Show Tracker Tip:</b> The NFC North concluded the previous season with all 4 teams over .500—making this standings block a crucial anchor point for discussing target ceilings on the next episode.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# --- TOP DIVISION COMMAND STATS MAIN SECTION ---
st.markdown("### 📋 DIVISION INTELLIGENCE STATIONS")
tab_bears, tab_lions, tab_packers, tab_vikings = st.tabs(["🐻 Chicago Bears", "🦁 Detroit Lions", "🧀 Green Bay Packers", "🍇 Minnesota Vikings"])

teams_list = [
    ("Chicago Bears", tab_bears), 
    ("Detroit Lions", tab_lions), 
    ("Green Bay Packers", tab_packers), 
    ("Minnesota Vikings", tab_vikings)
]

for team_name, tab_obj in teams_list:
    with tab_obj:
        assets = TEAM_ASSETS[team_name]
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, {assets['bg_color']} 0%, #11141a 100%); padding: 25px; border-radius: 12px; border-left: 8px solid {assets['text_color']}; display: flex; align-items: center; margin-bottom: 25px;">
                <img src="{assets['logo']}" style="width: 90px; margin-right: 25px;">
                <div>
                    <h2 style="color: white; margin: 0; font-family: sans-serif; font-size: 28px; letter-spacing: 1px;">{team_name.upper()} REPORT</h2>
                    <p style="color: #CCCCCC; margin: 5px 0 0 0; font-family: sans-serif; font-size: 15px;">Top 5 Global Trend-Weighted Stories</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        data = load_dashboard_data(team_name)
        if data.empty:
            st.info("No recent data within our 8-day freshness window found. Hit Sync!")
        else:
            cols = st.columns(5)
            for idx, row in data.iterrows():
                with cols[idx]:
                    thumb_url = row['thumbnail'] if ('thumbnail' in row and isinstance(row['thumbnail'], str) and row['thumbnail'].strip() != "") else assets['logo']
                    st.image(thumb_url, width='stretch')
                    
                    st.markdown(
                        f"""
                        <div style="height: 95px; margin-top: 10px; margin-bottom: 5px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;">
                            <a href="{row['link']}" target="_blank" style="text-decoration: none; color: #1f8fff; font-size: 16px; font-weight: bold; line-height: 1.3;">
                                {row['title']}
                            </a>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    
                    raw_date = row['fetched_at'] if row['fetched_at'] else ""
                    clean_date = raw_date.split(" 2026")[0] + " 2026" if " 2026" in raw_date else raw_date.split(" 2025")[0] + " 2025" if " 2025" in raw_date else raw_date
                    st.caption(f"🗓️ {clean_date}")
                    
                    with st.expander("📖 Read Summary", expanded=False):
                        if row['summary'] and row['summary'].strip() != "":
                            st.write(row['summary'])
                        else:
                            st.write("*No summary snippet provided by source.*")

st.markdown("---")

# --- SPLIT SCREEN PLATFORM LAYOUT ---
st.header("🎙️ Live Media Soundbites & Clips")

st.subheader("🎥 YouTube — NFC North clips")
render_media_cards(
    load_media_data(platform="youtube", limit=8),
    "No recent YouTube clips inside the 8-day window yet. Hit Sync!",
)

st.subheader("🐦 X / Twitter — Division posts")
render_media_cards(
    load_media_data(platform="x", limit=8),
    "No recent X posts captured yet. Hit Sync! (Requires a valid twitter_auth.json session.)",
)

st.sidebar.header("⚙️ Application Controls")
if st.sidebar.button("🔄 Sync Live Data Now"):
    with st.spinner("Executing Data Recalculation Engine..."):
        import agent
        agent.main()
    st.sidebar.success("Database successfully updated!")
    time.sleep(1)
    st.rerun()