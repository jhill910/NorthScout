import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import database
database.init_db()

# Set up page styling
st.set_page_config(page_title="NorthScout Dashboard", page_icon="🏈", layout="wide")

st.title("🏈 NorthScout: NFC North Master Show Prep App")
st.subheader(f"Weekly Data Sync — Snapshot for Week of {datetime.now().strftime('%B %d, %Y')}")
st.markdown("---")

# Sidebar options
st.sidebar.header("⚙️ Application Controls")
if st.sidebar.button("🔄 Sync Live Data Now"):
    with st.spinner("Re-calculating team trends and scraping feeds..."):
        import agent
        agent.main()
    st.sidebar.success("Database successfully updated!")

# Fetch fresh data from our local database
def load_dashboard_data(team_name):
    conn = sqlite3.connect("northscout.db")
    query = "SELECT title, link, fetched_at FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5"
    df = pd.read_sql_query(query, conn, params=(team_name,))
    conn.close()
    return df

# Create structural navigation tabs for each team on your interface
tab_bears, tab_lions, tab_packers, tab_vikings = st.tabs([
    "🐻 Chicago Bears", "🦁 Detroit Lions", "🧀 Green Bay Packers", "🍇 Minnesota Vikings"
])

teams_list = [
    ("Chicago Bears", tab_bears),
    ("Detroit Lions", tab_lions),
    ("Green Bay Packers", tab_packers),
    ("Minnesota Vikings", tab_vikings)
]

# Populate each layout tab with its popularity-sorted news lines
for team_name, tab_obj in teams_list:
    with tab_obj:
        st.header(f"Top 5 Trending Stories: {team_name}")
        data = load_dashboard_data(team_name)
        
        if data.empty:
            st.info("No data synced yet for this week. Hit the 'Sync Live Data Now' button in the sidebar!")
        else:
            for idx, row in data.iterrows():
                with st.container(border=True):
                    st.markdown(f"### 🔥 #{idx+1}: {row['title']}")
                    st.caption(f"Pulled into app on: {row['fetched_at']}")
                    st.markdown(f"[🔗 Open Source Link for Segment Content]({row['link']})")