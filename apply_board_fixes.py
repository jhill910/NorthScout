"""Patch 2026-09-16: event cap + division-order landing page.

WHY A SCRIPT, NOT REWRITTEN FILES
---------------------------------
Same reason as apply_scoring_fixes.py: three targeted replacements, each
asserted to match its anchor exactly once. If app.py or scoring.py has moved
on, this stops and changes nothing rather than overwriting newer work.

    python apply_board_fixes.py          # dry run
    python apply_board_fixes.py --write  # apply (.bak written first)

WHAT IT FIXES
-------------
1. EVENT CROWDING. Measured against the 9/15 rundown: 33 of the top 44
   Packers stories were the same Vikings game. The per-person cap could not
   see it, because those stories are about different people -- Matt LaFleur,
   Mike LaFleur, the team. So Tucker Kraft's extension (#31) and the Josh
   Jacobs update (#26) sat below the fold while the show discussed both.
   Capping game stories at three per column moved Pacheco #36 -> #11,
   Jacobs #26 -> #17, Kraft #31 -> #22, and top-5 accuracy 32% -> 39%.
   Three measured better than two, four or five.

2. NO DIVISION OVERVIEW. The show runs team by team, game first: Bears,
   Lions, Packers, Vikings. Producers had four tabs to scrub instead of the
   show's spine on one screen. On 9/15 the board's top story per team was
   right 4 for 4, so this surfaces something already reliable.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCORING = os.path.join(HERE, "scoring.py")
APP = os.path.join(HERE, "app.py")

SCORING_EDITS = [(
    "is_game_story helper",
    '''NOT_A_SCORE = re.compile(
    r"\\b(?:3-4|4-3|4-6|5-2|2-4|0-0)\\b|"
    r"\\b\\d{1,2}-\\d{1,2}\\s*(?:year|yr|season|game|week|day|man)\\b")
''',
    '''NOT_A_SCORE = re.compile(
    r"\\b(?:3-4|4-3|4-6|5-2|2-4|0-0)\\b|"
    r"\\b\\d{1,2}-\\d{1,2}\\s*(?:year|yr|season|game|week|day|man)\\b")


def is_game_story(title, summary=""):
    """True if this story is about a game that was played.

    score_story() works this out internally; app.py needs the same answer to
    stop one game filling a column, and two independent copies of the rule
    would drift apart. So it lives here and both callers use it.
    """
    blob = f" {str(title).lower()} {str(summary).lower()} "
    if _hits(blob, GAME_RECAP):
        return True
    return (bool(_SCORE_PATTERN.search(blob))
            and not NOT_A_SCORE.search(blob)
            and bool(_hits(blob, GAME_CONTEXT)))
''')]

APP_EDITS = [(
    "event cap function",
    '''def load_dashboard_data(team_name, limit=5):''',
    '''def _cap_event_cluster(df, max_game=3):
    """Stop one game from filling the whole column.

    _diversify() groups by the PEOPLE in a story, which cannot see an event.
    On 2026-09-15, 33 of the top 44 Packers stories were the same Vikings
    game -- written about Matt LaFleur, Mike LaFleur, Christian Watson and
    the team, so every one landed in a different person-cluster and none
    were capped. Tucker Kraft's extension, which the show gave a full
    question to, was the first non-game story in the column at #31.

    The week's game IS the lead -- three cards keep it there. Everything
    past three is deferred below, not dropped, so nothing is lost.

    Three was measured against the 9/15 rundown: it beat two, four and five
    on top-5 accuracy (39% vs 32% uncapped).
    """
    try:
        import scoring
    except ImportError:
        return df

    keep, deferred, n = [], [], 0
    for idx, row in df.iterrows():
        if scoring.is_game_story(row.get("title", ""), row.get("summary", "")):
            if n >= max_game:
                deferred.append(idx)
                continue
            n += 1
        keep.append(idx)
    return df.loc[keep + deferred]


def load_dashboard_data(team_name, limit=5):'''
), (
    "wire the cap into the pipeline",
    '''        df = _dedupe_near_titles(df)
        df = _diversify(df)
        return df.head(limit)[cols].reset_index(drop=True)''',
    '''        df = _dedupe_near_titles(df)
        df = _diversify(df)
        df = _cap_event_cluster(df)
        return df.head(limit)[cols].reset_index(drop=True)'''
), (
    "division-order landing page",
    '''# --- TOP DIVISION COMMAND STATS MAIN SECTION ---
st.markdown("### 📋 DIVISION INTELLIGENCE STATIONS")''',
    '''# --- THE RUNDOWN: top story per team, in division order --------------------
# The show is built team by team, game first: Bears, Lions, Packers, Vikings.
# Producers were opening four tabs to reconstruct that order every week. On
# 2026-09-15 the board's top story per team was correct for all four, so this
# puts the show's spine on one screen. The tabs below still hold the depth.
st.markdown("### 🎬 THE RUNDOWN &nbsp;<span style='font-size:13px;color:#8b949e;'>"
            "top story per team, in show order</span>", unsafe_allow_html=True)

_rundown_cols = st.columns(4)
for _col, _team in zip(_rundown_cols, ["Chicago Bears", "Detroit Lions",
                                       "Green Bay Packers", "Minnesota Vikings"]):
    _a = TEAM_ASSETS[_team]
    with _col:
        _df = load_dashboard_data(_team, limit=1)
        if _df is None or _df.empty:
            st.markdown(
                f"""<div style="background:{_a['bg_color']};border-radius:10px;padding:14px;
                       min-height:150px;"><div style="color:{_a['text_color']};font-weight:700;
                       font-size:13px;letter-spacing:0.06em;">{_team.split()[-1].upper()}</div>
                       <div style="color:#c9d1d9;font-size:13px;margin-top:10px;">
                       No stories in the current snapshot.</div></div>""",
                unsafe_allow_html=True)
            continue
        _r = _df.iloc[0]
        _title = str(_r.get("title") or "").replace("<", "&lt;")
        _link = str(_r.get("link") or "")
        _when = relative_time(_r.get("fetched_at"))
        _thumb = _r.get("thumbnail")
        _img = ""
        if isinstance(_thumb, str) and _thumb.strip() and not _thumb.endswith("bears-default.jpg"):
            _img = (f"<div style='height:84px;border-radius:6px;overflow:hidden;margin-bottom:10px;'>"
                    f"<img src='{_thumb}' style='width:100%;height:100%;object-fit:cover;"
                    f"display:block;'></div>")
        _headline = (f"<a href='{_link}' target='_blank' style='color:#ffffff;"
                     f"text-decoration:none;font-weight:600;font-size:14px;line-height:1.35;'>"
                     f"{_title}</a>") if _link else (
                     f"<span style='color:#ffffff;font-weight:600;font-size:14px;'>{_title}</span>")
        st.markdown(
            f"""<div style="background:{_a['bg_color']};border-radius:10px;padding:14px;
                   min-height:150px;box-shadow:0 0 12px {_a['glow']};">
                 <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                   <img src="{_a['logo']}" style="height:22px;width:22px;object-fit:contain;">
                   <span style="color:{_a['text_color']};font-weight:700;font-size:12px;
                          letter-spacing:0.06em;">{_team.split()[-1].upper()}</span>
                 </div>
                 {_img}
                 {_headline}
                 <div style="color:#8b949e;font-size:11px;margin-top:8px;">{_when}</div>
               </div>""",
            unsafe_allow_html=True)

st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

# --- TOP DIVISION COMMAND STATS MAIN SECTION ---
st.markdown("### 📋 DIVISION INTELLIGENCE STATIONS")'''
)]


def run(path, edits, label):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    print(f"\nChecking {label}:")
    bad = []
    for name, find, _ in edits:
        n = text.count(find)
        print(f"   {'ok ' if n == 1 else 'BAD'} {name:<32} anchor found {n}x")
        if n != 1:
            bad.append(name)
    if bad:
        return None, bad
    for _, find, repl in edits:
        text = text.replace(find, repl)
    return text, []


def main():
    write = "--write" in sys.argv
    for p in (SCORING, APP):
        if not os.path.exists(p):
            print(f"ERROR: {p} not found. Run this from inside the repo.")
            return 1

    if "def is_game_story" in open(SCORING, encoding="utf-8").read():
        print("   note: is_game_story already present -- already patched?")
        return 1

    new_scoring, bad1 = run(SCORING, SCORING_EDITS, "scoring.py")
    new_app, bad2 = run(APP, APP_EDITS, "app.py")
    if bad1 or bad2:
        print("\nSTOPPED -- nothing was changed. Anchors that did not match once:")
        for b in bad1 + bad2:
            print(f"   {b}")
        print("\nSend this output back rather than forcing it.")
        return 1

    if not write:
        print("\nAll anchors matched. Re-run with --write to apply:")
        print("   python apply_board_fixes.py --write")
        return 0

    shutil.copyfile(SCORING, SCORING + ".bak")
    shutil.copyfile(APP, APP + ".bak")
    with open(SCORING, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_scoring)
    with open(APP, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_app)
    print("\n   applied. Backups: scoring.py.bak / app.py.bak")
    print("\nNow:")
    print("   python test_scoring.py        # expect 20 oks, unchanged")
    print("   streamlit run app.py         # check THE RUNDOWN row up top")
    print("\nTo undo:  copy scoring.py.bak scoring.py & copy app.py.bak app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
