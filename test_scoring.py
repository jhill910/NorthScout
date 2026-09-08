"""Regression tests for scoring.py.

Each test pins a bug found while tuning against the 2026-09-01 rundown.
Run with:  python test_scoring.py
"""
from datetime import datetime
import scoring

NOW = datetime(2026, 9, 1, 21, 0)
FRESH = "Mon, 01 Sep 2026 18:00:00 GMT"
OLDER = "Sat, 30 Aug 2026 12:00:00 GMT"


def stats_for(stories):
    return scoring.build_corpus_stats(stories)


def s(title, summary="", pub=FRESH, link="", team="Chicago Bears", st=None):
    st = st or stats_for([{"title": title, "summary": summary, "pub": pub, "team": team}])
    return scoring.score_story(
        {"title": title, "summary": summary, "pub": pub, "link": link}, st, team, NOW)


def test_word_boundaries():
    """'sign' must not fire on 'Sign Contest'; 'ir' must not fire inside words."""
    assert scoring._hits(" the bears will sign a tackle ", scoring.TRANSACTION)
    assert not scoring._hits(" designing a first period ", ["sign"])
    assert not scoring._hits(" their first practice ", [" ir "])
    print("  ok  word-boundary matching")


def test_ceremonial_is_damped():
    """A charity story filed minutes ago must not outrank real news."""
    promo, _ = s("Bears celebrate third year of Girls Flag Football in the community")
    news, _ = s("Bears place Kyler Gordon on PUP with calf injury; no timetable")
    assert news > promo * 1.5, (news, promo)
    print(f"  ok  ceremonial damped ({promo:.1f}) vs availability news ({news:.1f})")


def test_longform_path_damped():
    a, _ = s("How Resiliency Keyed Larry Dean's Career", link="https://x.com/news/longform/larry-dean")
    b, _ = s("How Resiliency Keyed Larry Dean's Career", link="https://x.com/news/larry-dean")
    assert a < b, (a, b)
    print(f"  ok  /longform/ path damped ({a:.1f} vs {b:.1f})")


def test_attribution_needs_the_gm_on_record():
    """A GM name-checked in a press release is not attribution."""
    quoted, _ = s("Ryan Poles talks cutdown day", "General manager Ryan Poles said Saturday...")
    passing, _ = s("Bears unveil new scoreboard", "The project was approved while Ryan Poles watched.")
    assert quoted > passing, (quoted, passing)
    print(f"  ok  attribution requires being on the record ({quoted:.1f} vs {passing:.1f})")


def test_bylines_are_not_storylines():
    """A beat writer on every story is a byline, not a running storyline."""
    docs = [{"title": f"TWENTYMAN: Camp day {i}", "summary": "Tim Twentyman reports.",
             "pub": FRESH, "team": "Detroit Lions"} for i in range(10)]
    st = stats_for(docs)
    assert "Tim Twentyman" in st["staff"], st["staff"]
    print("  ok  beat writers classified as staff, excluded from momentum")


def test_non_people_rejected_as_entities():
    names = scoring.extract_names("Game Recap: Bears close preseason. General Manager Brian spoke.")
    assert "Game Recap" not in names and "General Manager" not in names, names
    assert scoring.extract_names("Caleb Williams looked sharp") == {"Caleb Williams"}
    print("  ok  non-person capitalised phrases rejected")


def test_recency_matters():
    new, _ = s("Bears sign a defensive back", pub=FRESH)
    old, _ = s("Bears sign a defensive back", pub=OLDER)
    assert new > old, (new, old)
    print(f"  ok  timeliness rewarded ({new:.1f} fresh vs {old:.1f} two days old)")


def test_uncertainty_and_conflict():
    plain, _ = s("Packers running back returns to practice")
    conflict, _ = s("Packers RB placed on Commissioner's Exempt List after misdemeanor charges")
    assert conflict > plain, (conflict, plain)
    print(f"  ok  off-field conflict outranks routine ({conflict:.1f} vs {plain:.1f})")


def test_rarity_no_longer_punishes_scoops():
    """The old model rewarded boilerplate vocabulary; the new one must not."""
    docs = [{"title": "Bears training camp report Thursday", "summary": "", "pub": FRESH,
             "team": "Chicago Bears"} for _ in range(20)]
    docs.append({"title": "Bears trade Gervon Dexter to Atlanta for Clark Phillips III",
                 "summary": "In exchange for a fifth-round pick.", "pub": FRESH,
                 "team": "Chicago Bears"})
    st = stats_for(docs)
    boiler, _ = scoring.score_story(docs[0], st, "Chicago Bears", NOW)
    scoop, _ = scoring.score_story(docs[-1], st, "Chicago Bears", NOW)
    assert scoop > boiler, (scoop, boiler)
    print(f"  ok  scoop outranks boilerplate ({scoop:.1f} vs {boiler:.1f})")


def test_charity_money_is_not_roster_money():
    """'Packers, Sargento teaming up to tackle hunger' held a card on 9/8."""
    st = stats_for([{"title": "x", "summary": "", "pub": FRESH, "team": "Green Bay Packers"}] * 4)
    charity, _ = scoring.score_story(
        {"title": "Packers, Sargento teaming up to tackle hunger in Wisconsin",
         "summary": "The partnership will donate $1 million to food banks.",
         "pub": FRESH, "link": ""}, st, "Green Bay Packers", NOW)
    real, _ = scoring.score_story(
        {"title": "Bears restructure Joe Thuney contract",
         "summary": "Chicago creates cap space.", "pub": FRESH, "link": ""},
        st, "Chicago Bears", NOW)
    assert real > charity * 1.5, (real, charity)
    print(f"  ok  charity money damped ({charity:.1f}) vs a real cap move ({real:.1f})")


def test_appearance_is_not_news():
    """'Bears GM Ryan Poles in attendance at Miami-Stanford game' hit #2 on 9/8."""
    st = stats_for([{"title": "x", "summary": "", "pub": FRESH, "team": "Chicago Bears"}] * 4)
    appearance, _ = scoring.score_story(
        {"title": "Bears GM Ryan Poles in attendance at Miami-Stanford game",
         "summary": "Poles was spotted at the college matchup.", "pub": FRESH, "link": ""},
        st, "Chicago Bears", NOW)
    onrecord, _ = scoring.score_story(
        {"title": "GM Ryan Poles: I don't know if Kyler Gordon will play this year",
         "summary": "Gordon opens the season on IR with a calf injury.",
         "pub": FRESH, "link": ""}, st, "Chicago Bears", NOW)
    assert onrecord > appearance * 2, (onrecord, appearance)
    print(f"  ok  appearance demoted ({appearance:.1f}) vs GM on record ({onrecord:.1f})")


def test_everyday_injury_language():
    """'hurt at practice' carried no availability signal at all on 9/8."""
    for phrase in ["hurt at practice", "missed practice", "ruled out",
                   "day-to-day", "rehabbing", "limited participant"]:
        assert scoring._hits(f" player {phrase} today ", scoring.AVAILABILITY), phrase
    print("  ok  everyday injury language recognised")


if __name__ == "__main__":
    print("scoring.py regression tests")
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("\nALL TESTS PASSED")
