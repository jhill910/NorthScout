"""Stop the roster from poisoning the routing.

THE BUG
-------
On 2026-10-06 the harvested "rosters" held 918 Chicago names, 708 Green Bay,
672 Minnesota, 553 Detroit. An NFL active roster is 53, plus 16 on the
practice squad. 260 names sat on ALL FOUR rosters -- Aaron Rodgers, Adam
Schefter, "An MRI", "Agent's Take" -- alongside "AP Second-Team", "AC Joint",
"Amundsen High School" and "Back-to-School Gifting".

It was a feedback loop:

    a wire story mentions an opposing player
      -> extract_from_entry() harvests that name onto this team's roster
        -> route_to_teams() now sends every story about that player here
          -> whose names are harvested too ...

Chicago has the most feeds, bootstrapped fastest, and ended up with 533 of
the 957 stories on the board -- including "Packers WR Jayden Reed undergoing
season-ending neck surgery". Minnesota was starved at 128. This is the same
root cause as Patrick Mahomes appearing in the Green Bay column on 09-22 and
a college football story in the Vikings column on 09-29.

THE FIX -- TWO INDEPENDENT GUARDS
---------------------------------
1. HARVEST ONLY FROM OFFICIAL CLUB FEEDS. bears.com names Bears; Yahoo names
   everybody. by_team already carries (entry, source) pairs and source
   carries "kind", so the gate is free. This cuts the loop at its source.

2. ROUTE ONLY ON TRUSTED NAMES. A name must be unique to one team and seen
   at least MIN_ROSTER_COUNT times before routing will act on it. Guard 1
   prevents new pollution; guard 2 means the pollution already on disk --
   and anything that slips past -- cannot misroute a story.

Deliberately NOT changed: extract_from_entry still reads headline text, but
now only ever sees official club entries, where a capitalised name is at
least plausibly that club's. Tightening the extractor as well is a separate
job and would be hard to verify in one sitting.

AFTER APPLYING, delete the poisoned file so it rebuilds clean:

    python fix_roster_pollution.py --write
    del data\\rosters.json
    git add roster.py agent.py fix_roster_pollution.py
    git commit -m "Harvest rosters from official feeds only; route on trusted names"
    git push

The next scrape rebuilds it from club feeds alone. Until it repopulates,
routing falls back to club terms, which is stricter than today, not looser.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROSTER = os.path.join(HERE, "roster.py")
AGENT = os.path.join(HERE, "agent.py")
TESTS = os.path.join(HERE, "test_roster.py")

ROSTER_EDITS = [(
    "harvest only official feeds",
    '''def harvest(by_team, rosters=None, today=None):
    """Update rosters from {team: [(entry, source), ...]}. Returns rosters."""
    rosters = rosters if rosters is not None else load_rosters()
    today = (today or datetime.now()).date().isoformat()

    for team, pairs in by_team.items():
        if team not in rosters:
            rosters[team] = {}
        bucket = rosters[team]
        for item in pairs:
            entry = item[0] if isinstance(item, tuple) else item
            for name in extract_from_entry(entry):''',
    '''def harvest(by_team, rosters=None, today=None, official_only=True):
    """Update rosters from {team: [(entry, source), ...]}. Returns rosters.

    official_only: harvest ONLY from a club's own feed. bears.com names
    Bears players; Yahoo and ProFootballTalk name the whole league. Without
    this gate every opposing player mentioned in a wire story joined the
    roster, and route_to_teams() then pulled that player's future news into
    this club's column -- whose names were harvested in turn. By 2026-10-06
    Chicago held 918 "roster" names and 533 of the board's 957 stories,
    including a Jayden Reed surgery story. Minnesota had 128.

    Set official_only=False only to reproduce the old behaviour in a test.
    """
    rosters = rosters if rosters is not None else load_rosters()
    today = (today or datetime.now()).date().isoformat()

    for team, pairs in by_team.items():
        if team not in rosters:
            rosters[team] = {}
        bucket = rosters[team]
        for item in pairs:
            entry = item[0] if isinstance(item, tuple) else item
            src = item[1] if isinstance(item, tuple) and len(item) > 1 else None
            if official_only:
                kind = (src or {}).get("kind") if isinstance(src, dict) else None
                if kind != "official":
                    continue
            for name in extract_from_entry(entry):'''
), (
    "trusted_names helper",
    '''def all_names(rosters=None, team=None):''',
    '''MIN_ROSTER_COUNT = 3


def trusted_names(rosters=None, min_count=MIN_ROSTER_COUNT):
    """{team: {lowercased names}} safe enough to ROUTE a story on.

    Two conditions, both learned from the 2026-10-06 board:

    1. UNIQUE TO ONE TEAM. A real player plays for one club. 260 names were
       on all four rosters -- Aaron Rodgers, Adam Schefter, "An MRI". Any
       name claimed by two clubs is ambiguous by definition and routing on
       it is a coin flip.

    2. SEEN AT LEAST min_count TIMES. 181 of Chicago's 918 names appeared
       exactly once, which is what a one-off mention or a mangled headline
       fragment looks like.

    This is deliberately separate from what gets STORED. Storage is cheap and
    reversible; a bad route silently puts another club's news on your board.
    """
    from collections import Counter
    rosters = rosters if rosters is not None else load_rosters()

    seen = Counter()
    for bucket in rosters.values():
        for name in bucket:
            seen[name.lower()] += 1

    out = {}
    for team, bucket in rosters.items():
        out[team] = {
            name.lower() for name, rec in bucket.items()
            if (rec.get("count", 0) if isinstance(rec, dict) else 0) >= min_count
            and seen[name.lower()] == 1
        }
    return out


def all_names(rosters=None, team=None):'''
)]

TEST_EDITS = [(
    "harvest test uses an official source",
    '''    r = roster.harvest({"Chicago Bears": [(e, None)]},
                       rosters={t: {} for t in roster.TEAMS}, today=today)
    assert "Coby Bryant" in r["Chicago Bears"]
    assert r["Chicago Bears"]["Coby Bryant"]["count"] == 1

    # second sighting a week later
    r = roster.harvest({"Chicago Bears": [(e, None)]}, rosters=r,
                       today=today + timedelta(days=7))
''',
    '''    # The source must now be the club's OWN feed -- see the harvest gate.
    OFFICIAL = {"kind": "official", "label": "Bears.com"}
    r = roster.harvest({"Chicago Bears": [(e, OFFICIAL)]},
                       rosters={t: {} for t in roster.TEAMS}, today=today)
    assert "Coby Bryant" in r["Chicago Bears"]
    assert r["Chicago Bears"]["Coby Bryant"]["count"] == 1

    # second sighting a week later
    r = roster.harvest({"Chicago Bears": [(e, OFFICIAL)]}, rosters=r,
                       today=today + timedelta(days=7))
'''
), (
    "new tests for the two guards",
    'if __name__ == "__main__":',
    '''def test_wire_sources_do_not_feed_the_roster():
    """The feedback loop that put Jayden Reed in the Chicago column.

    A wire story names the whole league. Harvesting from it put opposing
    players on a club roster, which then routed their future news here.
    """
    e = {"title": "Packers WR Jayden Reed undergoing neck surgery", "summary": "",
         "media_keywords": "Jayden Reed"}
    wire = {"kind": "wire", "label": "Yahoo"}
    r = roster.harvest({"Chicago Bears": [(e, wire)]},
                       rosters={t: {} for t in roster.TEAMS})
    assert not r["Chicago Bears"], r["Chicago Bears"]

    official = {"kind": "official", "label": "Bears.com"}
    r = roster.harvest({"Chicago Bears": [(e, official)]},
                       rosters={t: {} for t in roster.TEAMS})
    assert r["Chicago Bears"], "official feeds must still harvest"
    print("  ok  wire feeds cannot add to a roster; club feeds still can")


def test_trusted_names_rejects_shared_and_rare():
    """260 names sat on all four rosters; 181 were seen exactly once."""
    rosters = {
        "Chicago Bears": {
            "Caleb Williams": {"count": 9, "first_seen": "", "last_seen": ""},
            "Aaron Rodgers": {"count": 9, "first_seen": "", "last_seen": ""},
            "Seen Once Guy": {"count": 1, "first_seen": "", "last_seen": ""},
        },
        "Green Bay Packers": {
            "Aaron Rodgers": {"count": 9, "first_seen": "", "last_seen": ""},
        },
        "Detroit Lions": {}, "Minnesota Vikings": {},
    }
    t = roster.trusted_names(rosters, min_count=3)
    assert "caleb williams" in t["Chicago Bears"]
    assert "aaron rodgers" not in t["Chicago Bears"], "shared name must not route"
    assert "aaron rodgers" not in t["Green Bay Packers"]
    assert "seen once guy" not in t["Chicago Bears"], "one sighting must not route"
    print("  ok  routing ignores shared names and one-off sightings")


if __name__ == "__main__":'''
)]

# The test's own comment says "Harvest from a club feed item", so naming the
# source official makes it faithful to the new contract rather than weaker.
TEST_EDITS.append((
    "new-arrival test uses an official source",
    '''    r = roster.harvest({"Green Bay Packers": [(entry, None)]},
                       rosters={t: {} for t in roster.TEAMS})
''',
    '''    r = roster.harvest({"Green Bay Packers": [(entry, {"kind": "official"})]},
                       rosters={t: {} for t in roster.TEAMS})
'''
))

AGENT_EDITS = [(
    "route on trusted names",
    '''                import roster as _roster
                _r = _roster.load_rosters()
                roster_names = {t: {n.lower() for n in names}
                                for t, names in _r.items()}''',
    '''                import roster as _roster
                # trusted_names(), not every harvested string: a name must be
                # unique to one club and seen repeatedly before it is allowed
                # to route a story. See roster.trusted_names().
                _trusted = getattr(_roster, "trusted_names", None)
                if callable(_trusted):
                    roster_names = _trusted()
                else:
                    _r = _roster.load_rosters()
                    roster_names = {t: {n.lower() for n in names}
                                    for t, names in _r.items()}'''
)]


def run(label, path, edits, text):
    print(f"\nChecking {label}:")
    bad = []
    for name, find, _ in edits:
        n = text.count(find)
        print(f"   {'ok ' if n == 1 else 'BAD'} {name:<30} anchor found {n}x")
        if n != 1:
            bad.append(name)
    if bad:
        return None, bad
    for _, find, repl in edits:
        text = text.replace(find, repl)
    return text, []


def main():
    write = "--write" in sys.argv
    for p in (ROSTER, AGENT):
        if not os.path.exists(p):
            print(f"ERROR: {p} not found. Run this from inside the repo.")
            return 1
    rtext = open(ROSTER, encoding="utf-8").read()
    atext = open(AGENT, encoding="utf-8").read()
    if "def trusted_names" in rtext:
        print("   note: already patched.")
        return 1

    ttext = open(TESTS, encoding="utf-8").read()
    new_r, bad1 = run("roster.py", ROSTER, ROSTER_EDITS, rtext)
    new_a, bad2 = run("agent.py", AGENT, AGENT_EDITS, atext)
    new_t, bad3 = run("test_roster.py", TESTS, TEST_EDITS, ttext)
    if bad1 or bad2 or bad3:
        print("\nSTOPPED -- nothing changed. Send this output back.")
        return 1
    if not write:
        print("\nAll anchors matched. Re-run with --write to apply.")
        return 0

    shutil.copyfile(ROSTER, ROSTER + ".bak")
    shutil.copyfile(AGENT, AGENT + ".bak")
    shutil.copyfile(TESTS, TESTS + ".bak")
    with open(ROSTER, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_r)
    with open(AGENT, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_a)
    with open(TESTS, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_t)
    print("\n   applied. Backups: roster.py.bak / agent.py.bak")
    print("\n   NEXT, and this part matters -- delete the poisoned roster file:")
    print("      del data\\\\rosters.json")
    print("   The next scrape rebuilds it from club feeds only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
