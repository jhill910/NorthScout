"""Tests for the self-updating roster.

The headline test is test_new_arrival_becomes_visible: a player acquired this
week must be recognised in a national-show clip title without anyone editing a
list by hand. That is the failure that made Kaleb Johnson, Clark Phillips III,
Gervon Dexter and Coby Bryant invisible on 2026-09-01.

Run with:  python test_roster.py
"""

import sys
import types
from datetime import datetime, timedelta

# agent.py imports feedparser at module load; stub it so tests run anywhere.
_fp = types.ModuleType("feedparser")
_fp.parse = lambda *a, **k: None
sys.modules.setdefault("feedparser", _fp)

import roster
import scoring


def test_section_tags_rejected():
    junk = [
        "News: All News", "Article - Roster Moves", "Homepage CP",
        "Minicamp / OTAs / Training Camp", "NEWS - Twentyman",
        "Arizona Cardinals at Green Bay Packers (2026-PRE-3)",
        "Green Bay Packers", "Denver Broncos", "Rivalries Uniform",
        "Live Look-In", "Sign Contest", "ChicagoBears.com. This",
    ]
    for j in junk:
        assert not roster.looks_like_person(j), f"leaked: {j}"
    print(f"  ok  {len(junk)} section/noise tags rejected")


def test_real_names_accepted():
    good = ["Caleb Williams", "Kaleb Johnson", "Clark Phillips III",
            "Coby Bryant", "J. Michael Sturdivant", "Brian Gutekunst"]
    for g in good:
        assert roster.looks_like_person(g), f"wrongly rejected: {g}"
    print(f"  ok  {len(good)} real names accepted")


def test_position_prefixes_normalised():
    """'QB Kedon Slovis' and 'Kedon Slovis' must be the same person."""
    assert roster.normalise("QB Kedon Slovis") == "Kedon Slovis"
    assert roster.normalise("GM Brian Gutekunst") == "Brian Gutekunst"
    assert roster.normalise("Packers RB Kaleb Johnson") == "Kaleb Johnson"
    assert roster.normalise("Caleb Williams") == "Caleb Williams"
    print("  ok  club/position prefixes stripped, duplicates merged")


def test_extraction_from_headline():
    """The regex used to grab 'Packers RB Kaleb' and discard the whole run."""
    names = scoring.extract_names("5 things to know about new Packers RB Kaleb Johnson")
    assert names == {"Kaleb Johnson"}, names
    assert scoring.extract_names("Packers vs. Denver Broncos preseason recap") == set()
    print("  ok  names survive club/position prefixes; opponents excluded")


def test_harvest_accumulates_and_prunes():
    today = datetime(2026, 9, 1)
    e = {"title": "Bears activate Coby Bryant", "summary": "",
         "media_keywords": "Coby Bryant, Article - Roster Moves"}
    r = roster.harvest({"Chicago Bears": [(e, None)]},
                       rosters={t: {} for t in roster.TEAMS}, today=today)
    assert "Coby Bryant" in r["Chicago Bears"]
    assert r["Chicago Bears"]["Coby Bryant"]["count"] == 1

    # second sighting a week later
    r = roster.harvest({"Chicago Bears": [(e, None)]}, rosters=r,
                       today=today + timedelta(days=7))
    rec = r["Chicago Bears"]["Coby Bryant"]
    assert rec["count"] == 2 and rec["last_seen"] == "2026-09-08", rec

    # nobody has seen him in months -> he drops off, no manual edit needed
    removed = roster.prune(r, ttl_days=60, today=today + timedelta(days=200))
    assert removed == 1 and not r["Chicago Bears"], r
    print("  ok  accumulates across runs, prunes departures automatically")


def test_new_arrival_becomes_visible():
    """THE POINT OF ALL THIS.

    A player the show discussed but who was absent from the hand-typed keyword
    list must be picked up from the feeds and then recognised in a national
    clip title.
    """
    import agent

    clip = "Pat McAfee reacts to the Kaleb Johnson trade | The Pat McAfee Show"

    # Before: only the hardcoded core list exists.
    agent._ROSTER_CACHE = set(agent.STATIC_KEYWORDS) | set(agent.CORE_PEOPLE)
    assert not agent.is_nfc_north_relevant(clip), \
        "expected the old keyword list to miss this clip"

    # Harvest from a club feed item that mentions him.
    entry = {"title": "5 things to know about new Packers RB Kaleb Johnson",
             "summary": "Green Bay acquires backfield depth in trade with Pittsburgh",
             "media_keywords": ""}
    r = roster.harvest({"Green Bay Packers": [(entry, None)]},
                       rosters={t: {} for t in roster.TEAMS})
    assert "Kaleb Johnson" in r["Green Bay Packers"], r["Green Bay Packers"]

    # After: the harvested roster feeds the relevance filter.
    agent._ROSTER_CACHE = (set(agent.STATIC_KEYWORDS) | set(agent.CORE_PEOPLE)
                           | roster.all_names(r))
    assert agent.is_nfc_north_relevant(clip), "clip still invisible after harvest"
    print("  ok  NEW ARRIVAL VISIBLE: clip missed before harvest, caught after")


def test_relevance_survives_missing_roster_file():
    """A broken or absent roster file must not disable the filter."""
    import agent
    agent._ROSTER_CACHE = None
    real = roster.all_names
    roster.all_names = lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    try:
        assert agent.is_nfc_north_relevant("Bears open camp at Halas Hall")
    finally:
        roster.all_names = real
        agent._ROSTER_CACHE = None
    print("  ok  falls back to core list if the roster file is unreadable")


if __name__ == "__main__":
    print("roster tests")
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("\nALL TESTS PASSED")
