import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# Initialize database
import database
database.init_db()

st.set_page_config(page_title="NorthScout Dashboard", page_icon="🏈", layout="wide")

st.title("🏈 NorthScout: NFC North Master Show Prep App")
st.subheader(f"Weekly Data Sync — Snapshot for Week of {datetime.now().strftime('%B %d, %Y')}")
st.markdown("---")

st.sidebar.header("⚙️ Application Controls")
if st.sidebar.button("🔄 Sync Live Data Now"):
    with st.spinner("Executing RPA Engines & Recalculating Trends..."):
        import agent
        agent.main()
    st.sidebar.success("Database successfully updated!")

# Function to load Team News
def load_dashboard_data(team_name):
    conn = sqlite3.connect("northscout.db")
    query = "SELECT title, summary, link, fetched_at FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5"
    df = pd.read_sql_query(query, conn, params=(team_name,))
    conn.close()
    return df

# Function to load X Media Bites
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
        "bg_color": "#0B162A", "text_color": "#E64303"
    },
    "Detroit Lions": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
        "bg_color": "#0076B6", "text_color": "#B0B7BC"
    },
    "Green Bay Packers": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
        "bg_color": "#203731", "text_color": "#FFB612"
    },
    "Minnesota Vikings": {
        "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
        "bg_color": "#4F2683", "text_color": "#FFC62F"
    }
}

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
                background: linear-gradient(135deg, {assets['bg_color']} 0%, #1A1A1A 100%);
                padding: 25px;
                border-radius: 12px;
                border-left: 8px solid {assets['text_color']};
                display: flex;
                align-items: center;
                margin-bottom: 25px;
            ">
                <img src="{assets['logo']}" style="width: 100px; margin-right: 25px;">
                <div>
                    <h2 style="color: white; margin: 0; font-family: sans-serif; font-size: 28px;">{team_name} Dashboard</h2>
                    <p style="color: #CCCCCC; margin: 5px 0 0 0; font-family: sans-serif; font-size: 16px;">Top 5 Global Trend-Weighted Stories</p>
                </div>
            </div>
        """)
        
        data = load_dashboard_data(team_name)
        
        if data.empty:
            st.info("No data synced yet. Hit the Sync button!")
        else:
            for idx, row in data.iterrows():
                # Outer white container card for high contrast layout visibility
                with st.container(border=True):
                    st.markdown(f"#### 🔥 #{idx+1}: {row['title']}")
                    
                    # Inside expander for dynamic content
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
st.header("🎙️ Live Media Soundbites & Clips (X/Twitter)")

media_df = load_media_data()
if media_df.empty:
    st.info("No social media soundbites captured yet. Run the sync tool to deploy the RPA browser!")
else:
    cols = st.columns(3)
    for idx, row in media_df.iterrows():
        col_idx = idx % 3
        with cols[col_idx]:
            with st.container(border=True):
                st.markdown(f"### 📢 {row['source']}")
                st.caption(f"🕒 Original Post Time: {row['fetched_at']}")
                
                if row['tweet_text']:
                    st.markdown(f"*{row['tweet_text']}*")
                else:
                    st.markdown("*[No text content captured]*")
                
                st.markdown("---")
                st.markdown(f"[🎥 View Specific Post on X.com]({row['link']})")