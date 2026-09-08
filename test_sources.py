"""Tests for the source registry, wire routing and presser classification."""
import sys, types
_fp=types.ModuleType("feedparser"); _fp.parse=lambda *a,**k:None; sys.modules["feedparser"]=_fp
import sources, agent

def test_registry_shape():
    for label,url,team,kind,status in sources.SOURCES:
        assert kind in ("official","blog","paper","wire"), (label,kind)
        assert status in ("verified","unverified","disabled"), (label,status)
        assert team=="division" or team in sources.TEAM_ROUTING, (label,team)
        assert url.startswith("https://"), label
    print(f"  ok  registry well-formed ({len(sources.SOURCES)} feeds)")

def test_wire_routing():
    assert sources.route_to_teams(
        "Packers RB Josh Jacobs placed on Commissioner's Exempt List") == ["Green Bay Packers"]
    assert sources.route_to_teams("Chiefs sign a kicker") == []
    both = sources.route_to_teams("Bears trade Gervon Dexter to Atlanta; Lions claim him next")
    assert "Chicago Bears" in both and "Detroit Lions" in both, both
    print("  ok  wire routing (Jacobs -> Packers, AFC news dropped, multi-team ok)")

def test_jacobs_would_now_be_reachable():
    """The story that was structurally unreachable on 9/1."""
    headline = "Packers RB Josh Jacobs placed on Commissioner's Exempt List after misdemeanor charges"
    assert sources.route_to_teams(headline) == ["Green Bay Packers"]
    import scoring
    from datetime import datetime
    st = scoring.build_corpus_stats([{"title":headline,"summary":"","pub":"Mon, 01 Sep 2026 12:00:00 GMT","team":"Green Bay Packers"}])
    sc,rs = scoring.score_story({"title":headline,"summary":"","pub":"Mon, 01 Sep 2026 12:00:00 GMT"},
                                st,"Green Bay Packers",datetime(2026,9,1,21,0))
    assert sc > 60, (sc,rs)
    assert any("conflict" in r for r in rs), rs
    print(f"  ok  Jacobs story routes AND scores highly ({sc:.1f}): {[r for r in rs if 'conflict' in r]}")

def test_live_misroutes_2026_09_03():
    """Two false positives observed on the first live run.

    1. 'scamming a company out of millions' routed to the Detroit Lions,
       because naive substring matching found 'lions' inside 'millions'.
    2. A Rams schedule piece routed to Green Bay for naming the Packers once
       in passing.
    """
    assert sources.route_to_teams(
        "NFL legend Emmitt Smith accused in lawsuit of scamming company out of millions",
        "The Cowboys legend is in hot water after being hit with a lawsuit this week") == []
    assert sources.route_to_teams(
        "When did the Rams last beat teams on the 2026 schedule?",
        "LA is seeking to end lengthy losing streaks against the Eagles, Cowboys and Packers") == []
    # ...without breaking genuine multi-club routing
    assert sources.route_to_teams(
        "NFC North preview: Packers and Vikings both improved",
        "Green Bay and Minnesota look strong. The Packers added depth; the Vikings did too."
    ) == ["Green Bay Packers", "Minnesota Vikings"]
    print("  ok  live misroutes fixed (millions/Lions, passing Packers mention)")


def test_open_threads_demoted():
    """A blog open thread ranked #1 on the live Bears board."""
    import scoring
    from datetime import datetime
    now = datetime(2026, 9, 3, 20, 0)
    st = scoring.build_corpus_stats([{"title": "x", "summary": "", "pub": "", "team": "Chicago Bears"}] * 3)
    pub = "Tue, 02 Sep 2026 12:00:00 GMT"
    thread, _ = scoring.score_story(
        {"title": "Bears Over Beers Happy Hour and Open Thread: Bears Trade Incoming?",
         "summary": "", "pub": pub, "link": ""}, st, "Chicago Bears", now)
    news, _ = scoring.score_story(
        {"title": "Bears to move S Coby Bryant to injured reserve, sign DT",
         "summary": "", "pub": pub, "link": ""}, st, "Chicago Bears", now)
    assert news > thread * 2, (news, thread)
    print(f"  ok  open thread demoted ({thread:.1f}) below real news ({news:.1f})")


def test_rival_club_owns_the_headline_2026_09_08():
    """A Cowboys story reached the Packers board on the first live week.

    'Cowboys' captains: Kenny Clark, Quinnen Williams, Dak Prescott' matched
    Green Bay because Kenny Clark was hardcoded to the Packers -- he had since
    moved to Dallas. Hand-typed rosters go stale exactly when players move,
    which is exactly when they are newsworthy.
    """
    assert sources.route_to_teams(
        "Cowboys' captains: Kenny Clark, Quinnen Williams, Dak Prescott, Brandon Aubrey",
        "Dallas named six captains for the 2026 season.") == []

    # A rival in the headline must not suppress a genuine NFC North story.
    assert sources.route_to_teams(
        "Cowboys trade for Packers DL Kenny Clark",
        "Green Bay sends Clark to Dallas. The Packers get an edge rusher."
    ) == ["Green Bay Packers"]

    # And ordinary division news is untouched.
    assert sources.route_to_teams(
        "Bears restructure Joe Thuney, Dayo Odeyingbo, T.J. Edwards contracts",
        "Chicago creates cap space.") == ["Chicago Bears"]
    print("  ok  rival club owns the headline (Kenny Clark / Cowboys)")


def test_no_player_names_hardcoded():
    """Routing must not depend on a hand-maintained roster."""
    stale_risk = ["kenny clark", "caleb williams", "jordan love", "justin jefferson",
                  "jared goff", "micah parsons", "josh jacobs"]
    for team, keys in sources.TEAM_ROUTING.items():
        for k in keys:
            assert k not in stale_risk, f"{k!r} hardcoded under {team}"
    print("  ok  no player names hardcoded in TEAM_ROUTING")


def test_presser_classification():
    cases=[("Ryan Poles Press Conference | Chicago Bears","Chicago Bears","presser","Ryan Poles"),
           ("Dan Campbell postgame vs. Colts","Detroit Lions","presser","Dan Campbell"),
           ("10/10 Instagram dump from Caleb 🔥","Chicago Bears","clip",""),
           ("Vikings Rookie Trivia Competition gets serious","Minnesota Vikings","clip","")]
    for title,team,ek,es in cases:
        k,s=agent.classify_media(title,team)
        assert k==ek and s==es, (title,k,s,ek,es)
    print("  ok  presser classification + speaker extraction")

def test_dedupe_collapses_same_story():
    import pandas as pd, importlib
    class M:
        def __init__(s,n="st"): s._n=n; s._count=4
        def __call__(s,*a,**k):
            m=M(s._n)
            if a and isinstance(a[0],(list,tuple)): m._count=len(a[0])
            elif a and isinstance(a[0],int): m._count=a[0]
            return m
        def __getattr__(s,k):
            if k=="cache_data":
                def d(*a,**kw):
                    if a and callable(a[0]): f=a[0]; f.clear=lambda:None; return f
                    def i(f): f.clear=lambda:None; return f
                    return i
                return d
            return M(f"{s._n}.{k}")
        def __getitem__(s,i): return M(s._n)
        def __enter__(s): return s
        def __exit__(s,*a): return False
        def __iter__(s): return iter([M() for _ in range(s._count)])
        def __bool__(s): return False
    sys.modules["streamlit"]=M()
    import app
    df=pd.DataFrame([
        {"title":"Bears trade Gervon Dexter to Atlanta Falcons","score":50},
        {"title":"Bears trade Gervon Dexter to the Atlanta Falcons","score":45},
        {"title":"Report: Bears deal Gervon Dexter for fifth-rounder","score":40},
        {"title":"Ryan Poles talks cutdown day","score":38}])
    out=app._dedupe_near_titles(df)
    assert len(out)==3, out["title"].tolist()
    assert out.iloc[0]["score"]==50
    print(f"  ok  near-duplicate collapse ({len(df)} rows -> {len(out)}, kept highest score)")

if __name__=="__main__":
    print("source registry + presser tests")
    for f in list(globals().values()):
        if callable(f) and getattr(f,"__name__","").startswith("test_"): f()
    print("\nALL TESTS PASSED")
