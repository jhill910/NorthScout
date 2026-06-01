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
    query = "SELECT title, link, fetched_at FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5"
    df = pd.read_sql_query(query, conn, params=(team_name,))
    conn.close()
    return df

# Function to load X Media Bites
def load_media_data():
    conn = sqlite3.connect("northscout.db")
    query = "SELECT source, link, fetched_at FROM media_bites ORDER BY id DESC LIMIT 6"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

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
        st.header(f"Top 5 Trending Stories: {team_name}")
        data = load_dashboard_data(team_name)
        
        if data.empty:
            st.info("No data synced yet. Hit the Sync button!")
        else:
            for idx, row in data.iterrows():
                with st.container(border=True):
                    st.markdown(f"### 🔥 #{idx+1}: {row['title']}")
                    st.markdown(f"[🔗 Open Source Link]({row['link']})")

st.markdown("---")
st.header("🎙️ Live Media Soundbites & Clips (X/Twitter)")

# Load the fresh RPA scraped clips
media_df = load_media_data()
if media_df.empty:
    st.info("No social media soundbites captured yet. Run the sync tool to deploy the RPA browser!")
else:
    # Display them beautifully in a responsive 3-column grid layout
    cols = st.columns(3)
    for idx, row in media_df.iterrows():
        col_idx = idx % 3
        with cols[col_idx]:
            with st.container(border=True):
                st.markdown(f"### 📢 {row['source']}")
                st.caption(f"Captured: {row['fetched_at']}")
                st.markdown(f"[🎥 View Raw Video/Post on X.com]({row['link']})")