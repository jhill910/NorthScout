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
    query = "SELECT title, summary, link, fetched_at FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5"
    df = pd.read_sql_query(query, conn, params=(team_name,))
    conn.close()
    return df

def load_media_data():
    conn = sqlite3.connect("northscout.db")
    query = "SELECT source, tweet_text, link, fetched_at FROM media_bites ORDER BY id DESC LIMIT 9"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

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
# This single block explicitly identifies each tab index child so they highlight uniquely!
st.markdown(
    """
    <style>
        /* Base uniform style for all tabs when unselected */
        button[id*="tab"] {
            background-color: #11141a !important;
            color: #8b949e !important;
            transition: all 0.25s ease-in-out;
            font-size: 15px !important;
        }
        
        /* Individual dynamic target hooks based on placement index order */
        button[id*="tab-0"][aria-selected="true"] {
            border-bottom: 4px solid #E64303 !important;
            color: white !important;
            background-color: #0B162A !important;
            font-weight: bold !important;
        }
        button[id*="tab-1"][aria-selected="true"] {
            border-bottom: 4px solid #B0B7BC !important;
            color: white !important;
            background-color: #0076B6 !important;
            font-weight: bold !important;
        }
        button[id*="tab-2"][aria-selected="true"] {
            border-bottom: 4px solid #FFB612 !important;
            color: white !important;
            background-color: #203731 !important;
            font-weight: bold !important;
        }
        button[id*="tab-3"][aria-selected="true"] {
            border-bottom: 4px solid #FFC62F !important;
            color: white !important;
            background-color: #4F2683 !important;
            font-weight: bold !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- TOP BROADCAST REFRESH TICKER ---
st.markdown(
    f"""
    <div style="background: #11141a; padding: 18px; border-radius: 10px; border-bottom: 4px solid #E64303; text-align: center; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
        <h2 style="margin: 0; color: #ffffff; font-family: 'Courier New', monospace; letter-spacing: 3px; font-weight: bold;">{get_countdown_to_kickoff()}</h2>
        <p style="margin: 6px 0 0 0; color: #8b949e; font-size: 13px; font-family: sans-serif; letter-spacing: 1px;">NORTHSCOUT PLATINUM SHOW PREP PORTAL</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🏈 NorthScout: Master Show Prep App")
st.subheader(f"Snapshot Room — Week of {datetime.now().strftime('%B %d, %Y')}")
st.markdown("---")

# --- SIDEBAR INTERFACE MANIFEST ---
st.sidebar.header("⚙️ Application Controls")
if st.sidebar.button("🔄 Sync Live Data Now"):
    with st.spinner("Executing RPA Engines & Recalculating Trends..."):
        import agent
        agent.main()
    st.sidebar.success("Database successfully updated!")
    time.sleep(1)
    st.rerun()

# --- TOP DIVISION COMMAND STATS MAIN SECTION ---
st.markdown("### 📋 DIVISION INTELLIGENCE STATIONS")

# Team Navigation Tabs
tab_bears, tab_lions, tab_packers, tab_vikings = st.tabs([
    "🐻 Chicago Bears", "🦁 Detroit Lions", "🧀 Green Bay Packers", "🍇 Minnesota Vikings"
])

teams_list = [
    ("Chicago Bears", tab_bears),
    ("Detroit Lions", tab_lions),
    ("Green Bay Packers", tab_packers),
    ("Minnesota Vikings", tab_vikings)
]

for team_name, tab_obj in teams_list:
    with tab_obj:
        assets = TEAM_ASSETS[team_name]
        
        # Isolated HTML header block using team colors
        st.html(f"""
            <div style="
                background: linear-gradient(135deg, {assets['bg_color']} 0%, #11141a 100%);
                padding: 25px;
                border-radius: 12px;
                border-left: 8px solid {assets['text_color']};
                display: flex;
                align-items: center;
                margin-bottom: 25px;
                box-shadow: 0 4px 20px {assets['glow']};
            ">
                <img src="{assets['logo']}" style="width: 90px; margin-right: 25px;">
                <div>
                    <h2 style="color: white; margin: 0; font-family: sans-serif; font-size: 28px; letter-spacing: 1px;">{team_name.upper()} REPORT</h2>
                    <p style="color: #CCCCCC; margin: 5px 0 0 0; font-family: sans-serif; font-size: 15px;">Top 5 Global Trend-Weighted Stories</p>
                </div>
            </div>
        """)
        
        data = load_dashboard_data(team_name)
        
        if data.empty:
            st.info("No data synced yet. Hit the Sync button in the sidebar!")
        else:
            for idx, row in data.iterrows():
                with st.container(border=True):
                    st.markdown(f"#### 🔥 #{idx+1}: {row['title']}")
                    
                    with st.expander("📖 View Story Details & Outbound Source Link", expanded=False):
                        st.write(" ")
                        st.markdown("**📝 Story Preview Summary:**")
                        
                        if row['summary'] and row['summary'].strip() != "":
                            st.write(row['summary'])
                        else:
                            st.write("*No dynamic summary snippet returned for this article feed entry.*")
                            
                        st.markdown("---")
                        st.markdown(f"🔗 **[Open Source Article Link]({row['link']})**")
                        st.caption(f"🗓️ Published by Source: {row['fetched_at']}")

st.markdown("---")

# --- SPLIT SCREEN PLATFORM LAYOUT ---
col_social, col_standings = st.columns([2.2, 1])

with col_social:
    st.header("🎙️ Live Media Soundbites & Clips (X/Twitter)")
    media_df = load_media_data()
    
    if media_df.empty:
        st.info("No social media soundbites captured yet. Run the sync tool to deploy the browser tracker!")
    else:
        sub_cols = st.columns(2)
        for idx, row in media_df.iterrows():
            sub_col_idx = idx % 2
            with sub_cols[sub_col_idx]:
                with st.container(border=True):
                    st.markdown(f"##### 📢 {row['source']}")
                    st.caption(f"🕒 Post Timestamp: {row['fetched_at']}")
                    
                    if row['tweet_text']:
                        st.markdown(f"*{row['tweet_text']}*")
                    else:
                        st.markdown("*[No text content captured]*")
                    
                    st.markdown("---")
                    st.markdown(f"[🎥 View Source Post]({row['link']})")

with col_standings:
    st.header("📊 Divisional Standings")
    st.caption("Baseline: Official 2025 Regular Season Final Metrics")
    
    st.markdown(
        """
        <table style="width:100%; border-collapse: collapse; margin-top: 15px; border-radius: 8px; overflow: hidden; background-color: #11141a; font-family: sans-serif; font-size: 14px;">
            <tr style="background-color: #1f242d; color: #8b949e; text-align: left; font-weight: bold;">
                <th style="padding: 12px 10px;">TEAM</th>
                <th style="padding: 12px 10px; text-align: center;">W-L-T</th>
                <th style="padding: 12px 10px; text-align: center;">DIV</th>
                <th style="padding: 12px 10px; text-align: center;">DIFF</th>
            </tr>
            <tr style="border-bottom: 1px solid #2d333b; color: #ffffff;">
                <td style="padding: 12px 10px; font-weight: bold; border-left: 4px solid #E64303;">🐻 CHI</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">11-6-0</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">2-4</td>
                <td style="padding: 12px 10px; text-align: center; color: #238636; font-weight: bold;">+26</td>
            </tr>
            <tr style="border-bottom: 1px solid #2d333b; color: #ffffff;">
                <td style="padding: 12px 10px; font-weight: bold; border-left: 4px solid #FFB612;">🧀 GB</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">9-7-1</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">4-2</td>
                <td style="padding: 12px 10px; text-align: center; color: #238636; font-weight: bold;">+31</td>
            </tr>
            <tr style="border-bottom: 1px solid #2d333b; color: #ffffff;">
                <td style="padding: 12px 10px; font-weight: bold; border-left: 4px solid #4F2683;">🍇 MIN</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">9-8-0</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">4-2</td>
                <td style="padding: 12px 10px; text-align: center; color: #238636; font-weight: bold;">+11</td>
            </tr>
            <tr style="color: #ffffff;">
                <td style="padding: 12px 10px; font-weight: bold; border-left: 4px solid #0076B6;">🦁 DET</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">9-8-0</td>
                <td style="padding: 12px 10px; text-align: center; font-family: monospace;">2-4</td>
                <td style="padding: 12px 10px; text-align: center; color: #238636; font-weight: bold;">+68</td>
            </tr>
        </table>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown(
        """
        <div style="background-color: #11141a; padding: 12px; border-radius: 6px; border: 1px solid #2d333b; margin-top: 15px;">
            <p style="margin: 0; font-size: 12px; color: #8b949e; line-height: 1.4;">
                💡 <b>Show Tracker Tip:</b> The NFC North concluded the previous season with all 4 teams over .500—making this standings block a crucial anchor point for discussing target ceilings on the next episode.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )