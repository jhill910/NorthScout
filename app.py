import sys
import os
# Force Python to read the absolute folder directory path before anything else runs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import sqlite3
import json
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

# --- DATA LOADING ENGINES ---
# Streamlit Community Cloud has an EPHEMERAL filesystem: anything written to
# disk is wiped on restart, redeploy or inactivity sleep. So SQLite cannot be
# the source of truth in production. The scheduled GitHub Action commits
# data/northscout.json to the repo, which IS durable, and the app reads that.
# Local SQLite remains the fallback so local development still works.
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "northscout.json")


@st.cache_data(ttl=300)
def load_snapshot():
    """Read the committed JSON snapshot. Returns None if absent/unreadable."""
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f)
        if not isinstance(snap, dict) or "team_news" not in snap:
            return None
        return snap
    except (json.JSONDecodeError, OSError):
        return None


def relative_time(raw):
    """'9h ago' rather than 'Mon, 01 Sep 2026 12:00:00 GMT'.

    A producer cares how fresh a story is, not the RFC-822 string.
    """
    import scoring
    dt = scoring.parse_date(raw)
    if not dt:
        return str(raw or "")[:16]
    mins = (datetime.now() - dt).total_seconds() / 60
    if mins < 0:
        return "just now"
    if mins < 60:
        return f"{int(mins)}m ago"
    if mins < 48 * 60:
        return f"{int(mins // 60)}h ago"
    return f"{int(mins // 1440)}d ago"


# Signal -> (label, background, text colour). The scorer emits a long reasons
# sentence that gets truncated mid-thought on a card; these turn it into
# something scannable in about two seconds.
CHIP_RULES = [
    ("availability:",        "availability",     "#FCEBEB", "#A32D2D"),
    ("conflict:",            "off-field",        "#FCEBEB", "#A32D2D"),
    ("decision-maker",       "GM on record",     "#EEEDFE", "#534AB7"),
    ("front-office",         "coaching voice",   "#EEEDFE", "#534AB7"),
    ("press conference",     "press conference", "#E1F5EE", "#0F6E56"),
    ("uncertainty:",         "uncertainty",      "#FAEEDA", "#854F0B"),
    ("acquisition:",         "acquisition",      "#E6F1FB", "#185FA5"),
    ("roster milestone:",    "roster milestone", "#E6F1FB", "#185FA5"),
    ("transaction:",         "transaction",      "#E6F1FB", "#185FA5"),
    ("money:",               "money",            "#EAF3DE", "#3B6D11"),
    ("running storyline:",   "running story",    "#F1EFE8", "#5F5E5A"),
    ("independent source",   "independent",      "#F1EFE8", "#5F5E5A"),
    ("routine",              "routine",          "#F1EFE8", "#888780"),
    ("ceremonial",           "ceremonial",       "#F1EFE8", "#888780"),
]


def signal_chips(reasons, limit=3):
    """Highest-value signals first, de-duplicated, capped."""
    low = str(reasons or "").lower()
    out, seen = [], set()
    for needle, label, bg, fg in CHIP_RULES:
        if needle in low and label not in seen:
            seen.add(label)
            out.append((label, bg, fg))
        if len(out) >= limit:
            break
    return out


def chips_html(reasons, limit=3):
    parts = []
    for label, bg, fg in signal_chips(reasons, limit):
        parts.append(
            f"<span style='font-size:11px;padding:2px 7px;border-radius:4px;"
            f"background:{bg};color:{fg};margin-right:4px;white-space:nowrap;'>{label}</span>")
    return "".join(parts)


def _dedupe_near_titles(df, threshold=0.82):
    """Collapse the same story reported by several outlets.

    Now that wires, blogs and papers sit alongside the club feed, one
    transaction can appear four times with near-identical headlines. Keep the
    highest-scoring version so the board shows four stories, not one story
    four times.
    """
    from difflib import SequenceMatcher
    import re as _re

    def norm(t):
        return _re.sub(r"[^a-z0-9 ]", "", str(t).lower()).strip()

    keep, seen = [], []
    for idx, row in df.iterrows():
        t = norm(row.get("title"))
        if any(SequenceMatcher(None, t, s).ratio() >= threshold for s in seen):
            continue
        seen.append(t)
        keep.append(idx)
    return df.loc[keep]


def load_dashboard_data(team_name, limit=5):
    """Top stories for a team, ranked by the score the scraper computed.

    This previously used ORDER BY id DESC -- insertion order -- which threw away
    the ranking agent.py had just calculated. Two orderings were fighting and
    the arbitrary one won.
    """
    cols = ["title", "summary", "link", "fetched_at", "thumbnail", "score", "reasons"]

    snap = load_snapshot()
    if snap is not None:
        rows = snap.get("team_news", {}).get(team_name, [])
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = 0 if c == "score" else ""
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
        df = df.sort_values("score", ascending=False)
        df = _dedupe_near_titles(df)
        return df.head(limit)[cols].reset_index(drop=True)

    conn = sqlite3.connect(database.DB_NAME)
    query = """
        SELECT title, summary, link, fetched_at, thumbnail,
               COALESCE(score, 0) AS score, COALESCE(reasons, '') AS reasons
        FROM team_news
        WHERE team = ?
        ORDER BY score DESC, id DESC
        LIMIT ?
    """
    df = pd.read_sql_query(query, conn, params=(team_name, limit * 3))
    conn.close()
    return _dedupe_near_titles(df).head(limit).reset_index(drop=True)


def load_media_data(platform=None, limit=8, kind=None):
    snap = load_snapshot()
    if snap is not None:
        rows = snap.get("media_bites", [])
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["source", "tweet_text", "link", "fetched_at", "platform",
                     "kind", "speaker"])
    else:
        conn = sqlite3.connect(database.DB_NAME)
        query = """
            SELECT source, tweet_text, link, fetched_at,
                   COALESCE(platform, '') AS platform,
                   COALESCE(kind, 'clip') AS kind,
                   COALESCE(speaker, '') AS speaker
            FROM media_bites
            ORDER BY id DESC
            LIMIT 120
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

    if df.empty:
        return df

    def infer_platform(row):
        tagged = str(row.get("platform") or "").strip().lower()
        if tagged in ("youtube", "x", "bluesky"):
            return tagged
        link = str(row.get("link") or "").lower()
        if "youtube.com" in link or "youtu.be" in link:
            return "youtube"
        if "x.com" in link or "twitter.com" in link:
            return "x"          # legacy rows from before X was disabled
        if "bsky.app" in link:
            return "bluesky"
        return ""

    for c in ("kind", "speaker"):
        if c not in df.columns:
            df[c] = "clip" if c == "kind" else ""

    df["_platform"] = df.apply(infer_platform, axis=1)
    if platform:
        df = df[df["_platform"] == platform]
    if kind:
        df = df[df["kind"] == kind]
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


def render_freshness_banner():
    """Never let stale data pass as current. Every failure used to be a silent
    print() to a console nobody sees; now the age of the data is on screen."""
    snap = load_snapshot()
    if snap is None:
        st.warning(
            "⚠️ **No committed snapshot found.** Falling back to local SQLite, which "
            "does **not** survive restarts on Streamlit Cloud. Check that the "
            "`scrape.yml` GitHub Action has run and committed `data/northscout.json`."
        )
        return
    try:
        gen = datetime.fromisoformat(str(snap.get("generated_at", "")).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600
        stamp = gen.strftime("%b %d, %Y at %H:%M UTC")
    except ValueError:
        st.warning("⚠️ Snapshot found but its timestamp is unreadable.")
        return

    counts = snap.get("counts", {})
    detail = (f"{counts.get('team_news', 0)} stories · "
              f"{counts.get('media_bites', 0)} media bites · scraped {stamp}")
    if age_h < 24:
        st.success(f"✅ Data is current — {detail}")
    elif age_h < 72:
        st.warning(f"⚠️ Data is {age_h/24:.1f} days old — {detail}")
    else:
        st.error(
            f"🛑 Data is {age_h/24:.1f} days old — {detail}. "
            "The scheduled scrape has likely stopped. Check the Actions tab."
        )


render_freshness_banner()
st.markdown("---")

# --- DIVISION STANDINGS (live) ---------------------------------------------
# These used to be hardcoded HTML: Bears 11-6-0, Packers 9-7-1, and so on --
# the 2025 FINAL records, displayed under a header reading "division
# standings" on a desk used during production. In September 2026 everyone is
# 0-0, so anyone glancing at it read numbers that were plausible and wrong.
# Now it shows the real thing, or admits it doesn't have it.


@st.cache_data(ttl=900)
def load_standings():
    snap = load_snapshot() or {}
    embedded = snap.get("standings")
    if embedded and embedded.get("teams"):
        return embedded
    try:
        import standings as standings_mod
        return standings_mod.load_cached()
    except Exception:
        return None


_st = load_standings()

st.markdown("### 📊 DIVISION STANDINGS")

if not _st or not _st.get("teams"):
    st.warning(
        "⚠️ **Standings unavailable.** The live feed didn't return data on the "
        "last run. Showing nothing beats showing last season's numbers as if "
        "they were current — run `python standings.py` to check the source."
    )
else:
    _teams = _st["teams"]
    _order = sorted(
        TEAM_ASSETS.keys(),
        key=lambda t: (-(_teams.get(t, {}).get("wins") or 0),
                       _teams.get(t, {}).get("losses") or 0),
    )
    _cards = []
    for _t in _order:
        _rec = _teams.get(_t, {})
        _a = TEAM_ASSETS[_t]
        _record = _rec.get("record") or "—"
        _diff = _rec.get("point_diff")
        if _diff is None:
            _diff_s, _diff_c = "—", "#8b949e"
        else:
            _diff_s = f"+{_diff}" if _diff > 0 else str(_diff)
            _diff_c = "#238636" if _diff > 0 else ("#8b949e" if _diff == 0 else "#d1444a")
        _cards.append(
            f"""<div style="text-align:center;min-width:150px;flex:1;
                            border-right:1px solid #1f2d42;padding:0 10px;">
                  <h5 style="color:#8b949e;margin:0;font-size:12px;letter-spacing:1px;">
                    {_t.upper()}</h5>
                  <h2 style="color:{_a['text_color']};margin:5px 0 0;font-size:26px;
                             font-weight:bold;">{_record}</h2>
                  <span style="color:{_diff_c};font-size:12px;font-weight:bold;">
                    {_diff_s} diff</span>
                </div>"""
        )
    st.markdown(
        f"""
        <div style="background-color:#0B162A;padding:20px;border-radius:12px;
                    border-left:8px solid #E64303;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-around;align-items:center;
                      flex-wrap:wrap;gap:12px;">{''.join(_cards)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"🔄 {_st.get('source', 'live')} · updated {relative_time(_st.get('fetched_at'))}")

st.markdown("---")

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
        
        # Pull 10 and show 5 as cards. On a heavy news week one club can have
        # 40+ stories in window and five slots genuinely isn't enough -- the
        # 9/1 Packers board had four separate rundown topics competing for
        # five cards. Measured against that rundown, top-5 covered 12 of 13
        # discussed topics and top-8 covered all 13.
        data = load_dashboard_data(team_name, limit=10)
        if data.empty:
            st.info("No recent data within our 8-day freshness window found. Hit Sync!")
        else:
            def thumb_block(row, height, radius):
                """Real image if the feed gave one, otherwise a muted placeholder.

                The old fallback stretched the full-colour team logo into every
                card without a picture, so real photography had to compete with
                a wall of logos. Grey recedes; photos carry."""
                url = row.get("thumbnail")
                if isinstance(url, str) and url.strip() and not url.endswith("bears-default.jpg"):
                    return (f"<div style=\"height:{height}px;border-radius:{radius};overflow:hidden;"
                            f"background:#F1EFE8;\">"
                            f"<img src='{url}' style='width:100%;height:100%;object-fit:cover;"
                            f"display:block;'></div>")
                return (f"<div style=\"height:{height}px;border-radius:{radius};background:"
                        f"{assets['bg_color']}1A;display:flex;align-items:center;"
                        f"justify-content:center;\">"
                        f"<span style='font-size:13px;letter-spacing:0.08em;color:#888780;'>"
                        f"{team_name.split()[-1].upper()}</span></div>")

            lead = data.iloc[0]

            # --- lead story: full width, larger thumbnail --------------------
            st.markdown(
                f"""
                <div style="background:#ffffff;border:1px solid #e3e0d8;border-radius:12px;
                            padding:14px;display:flex;gap:16px;margin-bottom:18px;">
                  <div style="flex:0 0 220px;">{thumb_block(lead, 124, '8px')}</div>
                  <div style="flex:1;min-width:0;">
                    <div style="margin-bottom:6px;font-size:12px;color:#5F5E5A;">
                      <span style="background:{assets['bg_color']};color:#ffffff;font-size:11px;
                                   padding:2px 8px;border-radius:4px;margin-right:8px;">LEAD</span>
                      {relative_time(lead['fetched_at'])}
                    </div>
                    <a href="{lead['link']}" target="_blank"
                       style="font-size:19px;font-weight:600;color:#1f6feb;text-decoration:none;
                              line-height:1.3;display:block;margin-bottom:8px;">{lead['title']}</a>
                    <p style="font-size:14px;color:#3d3d3a;line-height:1.55;margin:0 0 10px;">
                      {str(lead['summary'])[:340]}</p>
                    <div>{chips_html(lead.get('reasons'), 4)}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("📋 Copy lead for the rundown", expanded=False):
                st.code(f"{lead['title']}\n{lead['link']}", language=None)

            # --- the rest: four across --------------------------------------
            rest = data.iloc[1:5].reset_index(drop=True)
            if not rest.empty:
                cols = st.columns(len(rest))
                for idx, row in rest.iterrows():
                    with cols[idx]:
                        st.markdown(
                            f"""
                            <div style="background:#ffffff;border:1px solid #e3e0d8;
                                        border-radius:12px;overflow:hidden;margin-bottom:8px;">
                              {thumb_block(row, 104, '0')}
                              <div style="padding:11px 12px 13px;">
                                <div style="font-size:12px;color:#5F5E5A;margin-bottom:5px;">
                                  <span style="color:#888780;">#{idx + 2}</span> ·
                                  {relative_time(row['fetched_at'])}
                                </div>
                                <a href="{row['link']}" target="_blank"
                                   style="font-size:14px;font-weight:600;color:#1f6feb;
                                          text-decoration:none;line-height:1.35;display:block;
                                          margin-bottom:6px;">{row['title']}</a>
                                <p style="font-size:12.5px;color:#3d3d3a;line-height:1.5;
                                          margin:0 0 8px;">{str(row['summary'])[:190]}</p>
                                <div>{chips_html(row.get('reasons'), 2)}</div>
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        with st.expander("📋 Copy", expanded=False):
                            st.code(f"{row['title']}\n{row['link']}", language=None)

            runners_up = data.iloc[5:]
            if not runners_up.empty:
                with st.expander(f"➕ {len(runners_up)} more stories in the window",
                                 expanded=False):
                    for _, row in runners_up.iterrows():
                        st.markdown(
                            f"**[{row['title']}]({row['link']})**  "
                            f"<span style='color:#8b949e;font-size:12px;'>"
                            f"· {relative_time(row['fetched_at'])}</span><br>"
                            f"{chips_html(row.get('reasons'), 3)}",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<hr style='margin:8px 0;border-color:#2d333b;'>",
                            unsafe_allow_html=True,
                        )

st.markdown("---")

# --- SPLIT SCREEN PLATFORM LAYOUT ---
st.header("🎙️ Live Media Soundbites & Clips")

# Every "==" break in the show rundown is a SOT. Pressers get their own rail so
# they can be scanned in one place while segments are being built, and they also
# rank inside the team tabs on their merits.
st.subheader("🎙️ Press Conferences & SOTs")
_pressers = load_media_data(kind="presser", limit=12)
if _pressers.empty:
    st.info(
        "No press conferences detected in the current window. Clubs post full "
        "availabilities to YouTube within hours of a presser — if this stays "
        "empty after a scrape, check that the team channel IDs in agent.py are "
        "still correct."
    )
else:
    _pcols = st.columns(3)
    for _i, _row in _pressers.iterrows():
        with _pcols[_i % 3]:
            with st.container(border=True):
                _who = _row.get("speaker") or "—"
                st.markdown(f"##### 🎙️ {_who}")
                st.caption(f"🕒 {_row['fetched_at']} · {_row['source']}")
                st.markdown(
                    f"[{str(_row['tweet_text'])[:110]}]({_row['link']})"
                )

st.markdown("---")

st.subheader("🎥 YouTube — NFC North clips")
render_media_cards(
    load_media_data(platform="youtube", limit=8, kind="clip"),
    "No recent YouTube clips inside the 8-day window yet. Hit Sync!",
)

st.subheader("🦋 Bluesky — Division posts")
render_media_cards(
    load_media_data(platform="bluesky", limit=8),
    "No recent Bluesky posts yet. Run `python check_bluesky.py` to confirm the "
    "API shape and that the configured handles resolve.",
)

st.sidebar.header("⚙️ Application Controls")

_snap = load_snapshot()
if _snap is not None:
    st.sidebar.caption(f"📦 Snapshot: {_snap.get('generated_at', 'unknown')}")
    st.sidebar.caption(f"🔁 Refreshed automatically by GitHub Actions")
else:
    st.sidebar.caption("📦 No committed snapshot — using local SQLite")

if st.sidebar.button("🔄 Sync Live Data Now"):
    with st.spinner("Scraping division feeds..."):
        try:
            import agent
            agent.main()
            st.sidebar.success("Local database updated.")
        except Exception as e:
            st.sidebar.error(f"Sync failed: {e}")
            raise
    load_snapshot.clear()
    time.sleep(1)
    st.rerun()

st.sidebar.info(
    "**Note:** a manual sync writes to local disk only. On Streamlit Cloud that "
    "disk is wiped on every restart, so manual syncs are temporary. Durable "
    "updates come from the scheduled GitHub Action, which commits "
    "`data/northscout.json` back to the repo."
)