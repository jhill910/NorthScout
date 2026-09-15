"""One-time patch: apply the 2026-09-15 scoring fixes to scoring.py.

WHY A SCRIPT INSTEAD OF A REWRITTEN FILE
----------------------------------------
The last clobber in this project happened because a stale working copy was
written over the real upstream. This script never writes a whole file. It
makes five targeted replacements, and every one asserts its anchor text
appears EXACTLY once first. If scoring.py has moved on, this stops with an
error and changes nothing -- it cannot silently overwrite newer work.

    python apply_scoring_fixes.py          # show what would change
    python apply_scoring_fixes.py --write  # actually change it

Safe to abandon at any point: --write makes a .bak of both files first.

WHAT IT FIXES
-------------
1. A bare number pair was treated as a final score. "3-4 defensive front",
   "1-2 year deal" and "0-0 record" each collected the full W_GAME_RECAP
   bonus -- the largest single weight in the scorer. A depth-chart story
   about scheme outranked a player landing on IR.
2. Undated stories never decayed. Having no decay factor, they drifted to
   the top of the board as every dated story around them aged, and stayed.
3. Game results decayed at the same rate as routine news, so Sunday's game
   had faded below roster chatter by the Tuesday taping. The week's game is
   the show's anchor; it now uses a much longer half-life.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCORING = os.path.join(HERE, "scoring.py")
TESTS = os.path.join(HERE, "test_scoring.py")

# ---------------------------------------------------------------------------
# (label, find, replace) -- each `find` must occur exactly once.
# ---------------------------------------------------------------------------
EDITS = [
    (
        "recap half-life constant",
        """# a several-day-old routine story still visibly fades next to something
# genuinely new. The GAME_RECAP/GAME_PREVIEW bonuses below (which are large
# and additive) are what keep an aging game story ahead of routine chatter,
# not an artificial decay exemption.
OVERALL_DECAY_HALFLIFE_H = 96.0   # 4 days
""",
        """# a several-day-old routine story still visibly fades next to something
# genuinely new.
OVERALL_DECAY_HALFLIFE_H = 96.0   # 4 days

# Game results get their own, much longer half-life.
#
# The earlier reasoning was that the large additive GAME_RECAP bonus would be
# enough to keep an aging game ahead of routine chatter without an "artificial
# decay exemption". Measured against the show calendar, it isn't. A Thursday
# night game is ~114h old by the Tuesday taping; at a 96h half-life it retains
# ~44% of its score and lands BELOW a routine Monday signing. That inverts the
# actual rundown, where the week's game is the anchor the show is built around.
#
# So this is not an exemption from decay -- a game story still fades, and a
# month-old result is gone. It fades on the timescale a weekly show cares
# about rather than a daily news cycle's.
RECAP_DECAY_HALFLIFE_H = 480.0    # ~20 days
""",
    ),
    (
        "score pattern needs game context",
        '''_SCORE_PATTERN = re.compile(r"\\b\\d{1,2}-\\d{1,2}\\b")
''',
        '''_SCORE_PATTERN = re.compile(r"\\b\\d{1,2}-\\d{1,2}\\b")

# A bare number pair is NOT a final score. On its own the pattern above fires
# on a 3-4 defensive front, a 1-2 year deal and an 0-0 record -- each of which
# collected the full W_GAME_RECAP bonus, the largest single weight here. So a
# depth-chart story about scheme outscored a player landing on IR.
#
# Requiring a game word nearby costs almost nothing (a real recap always has
# one) and removes the whole class of false positives.
GAME_CONTEXT = [
    "final", "beat", "beats", "defeat", "defeats", "defeated", "win", "wins",
    "won", "loss", "lose", "loses", "lost", "victory", "recap", "halftime",
    "quarter", "overtime", "comeback", "rally", "upset", "shutout",
    "improve to", "fall to", "falls to", "drop to", "drops to", "vs.", " vs ",
    " at ", "week 1", "week 2", "week 3", "week 4", "week 5", "week 6",
]

# Number pairs that are never a score, even with a game word in the sentence:
# football formations, and any pair followed by a unit ("2-4 year deal").
NOT_A_SCORE = re.compile(
    r"\\b(?:3-4|4-3|4-6|5-2|2-4|0-0)\\b|"
    r"\\b\\d{1,2}-\\d{1,2}\\s*(?:year|yr|season|game|week|day|man)\\b")
''',
    ),
    (
        "detect the game before timeliness",
        """    score = 0.0
    reasons = []
    decay_factor = 1.0
""",
        """    score = 0.0
    reasons = []
    story_age_h = None

    # Is this a game result? Detected up here rather than in its own block
    # below because BOTH the recency term and the final decay need to know.
    # Scoring it later meant a Thursday night game had its recency term
    # computed on the 34h news half-life -- 114h old by the Tuesday taping
    # leaves 3% of 42 points, about 1.5 -- and a 30-point recap bonus cannot
    # cover that gap against a routine Monday signing that is six hours old.
    # The game is what the show is built around, so it decays on the show's
    # weekly clock, not the news cycle's daily one.
    gr = _hits(blob, GAME_RECAP)
    has_score_pattern = (
        bool(_SCORE_PATTERN.search(blob))
        and not NOT_A_SCORE.search(blob)
        and bool(_hits(blob, GAME_CONTEXT))
    )
    is_game = bool(gr or has_score_pattern)
""",
    ),
    (
        "undated stories decay too",
        """        age_h = max((now - dt).total_seconds() / 3600.0, 0.0)
        rec = W_RECENCY * math.exp(-age_h / RECENCY_HALFLIFE_H)
        score += rec
        if rec >= 4:
            if age_h < 24:
                reasons.append(f"published {age_h:.0f}h ago")
            else:
                reasons.append(f"published {age_h/24:.1f}d ago")
        # Applied to the FULL score at return time below -- see
        # OVERALL_DECAY_HALFLIFE_H above for why this is continuous, not a
        # grace-period step function.
        decay_factor = math.exp(-age_h / OVERALL_DECAY_HALFLIFE_H)
    else:
        score += W_RECENCY * 0.3
""",
        """        age_h = max((now - dt).total_seconds() / 3600.0, 0.0)
        rec_halflife = RECAP_DECAY_HALFLIFE_H if is_game else RECENCY_HALFLIFE_H
        rec = W_RECENCY * math.exp(-age_h / rec_halflife)
        score += rec
        if rec >= 4:
            if age_h < 24:
                reasons.append(f"published {age_h:.0f}h ago")
            else:
                reasons.append(f"published {age_h/24:.1f}d ago")
        # Decay is applied to the FULL score at return time below, once we
        # know whether this is a game result -- see the two half-life
        # constants above.
        story_age_h = age_h
    else:
        # No usable date. Previously these got a flat partial credit and NO
        # decay factor at all, so they never faded: as every dated story
        # around them aged, an undated one drifted to the top of the board
        # and stayed there. Treat it as roughly three days old instead.
        score += W_RECENCY * 0.3
        story_age_h = 72.0
        reasons.append("undated -- treated as ~3 days old")
""",
    ),
    (
        "recap block uses the early detection",
        """    # --- game recap: usually the biggest story of the week -----------------
    gr = _hits(blob, GAME_RECAP)
    has_score_pattern = bool(_SCORE_PATTERN.search(blob))
    if gr or has_score_pattern:
""",
        """    # --- game recap: usually the biggest story of the week -----------------
    # gr / has_score_pattern were computed above, before the timeliness block.
    if is_game:
""",
    ),
    (
        "apply the right half-life",
        """    # Age decay applies last, over everything above -- so a story's stacked
    # signals fade with it instead of persisting at full strength indefinitely.
    score *= decay_factor
""",
        """    # Age decay applies last, over everything above -- so a story's stacked
    # signals fade with it instead of persisting at full strength indefinitely.
    # Game results use the longer half-life: by Tuesday the week's game is
    # days old but it is still what the show is built around.
    if story_age_h is not None:
        halflife = (RECAP_DECAY_HALFLIFE_H if is_game
                    else OVERALL_DECAY_HALFLIFE_H)
        score *= math.exp(-story_age_h / halflife)
""",
    ),
]

NEW_TESTS = '''

# ---------------------------------------------------------------------------
# Age decay and game detection (added 2026-09-15)
# ---------------------------------------------------------------------------

def _at(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M")


def _sc(title, summary="", hours_ago=2, team="Chicago Bears", st=None):
    story = {"title": title, "summary": summary, "team": team,
             "pub": _at(hours_ago), "link": ""}
    st = st or stats_for([story])
    return scoring.score_story(story, st, team, NOW)[0]


def test_fresh_news_beats_a_stacked_old_story():
    """Decay has to actually bite, or the board never turns over."""
    old = _sc("Bears sign guard to three-year extension worth $30 million",
              "General manager Ryan Poles confirmed the deal.", hours_ago=24 * 8)
    new = _sc("Bears place cornerback on injured reserve", hours_ago=3)
    assert new > old, f"8-day-old stacked story {old} >= fresh news {new}"
    print(f"  ok  decay turns the board over ({new:.1f} fresh vs {old:.1f} at 8d)")


def test_thursday_game_survives_to_tuesday_taping():
    """The week's game is the show's anchor; it must outlive routine news."""
    game = _sc("Packers beat Lions 27-13 on Thursday night",
               "Green Bay improves to 2-0.", hours_ago=114,
               team="Green Bay Packers")
    routine = _sc("Packers sign practice squad receiver", hours_ago=6,
                  team="Green Bay Packers")
    assert game > routine, f"game {game} faded below routine signing {routine}"
    print(f"  ok  Thursday game survives to Tuesday ({game:.1f} vs {routine:.1f})")


def test_decay_is_continuous_not_a_grace_window():
    """No cliff edge: each day older must score strictly lower."""
    vals = [_sc("Bears place cornerback on injured reserve", hours_ago=h)
            for h in (2, 26, 50, 98, 170)]
    assert all(a > b for a, b in zip(vals, vals[1:])), vals
    print("  ok  decay is continuous: " + " > ".join(f"{v:.1f}" for v in vals))


def test_game_recap_signal():
    recap = _sc("Lions defeat Bears 31-24", "Detroit improves to 2-0.",
                team="Detroit Lions")
    plain = _sc("Lions hold walkthrough at practice facility",
                team="Detroit Lions")
    assert recap > plain
    print(f"  ok  game recap outranks routine ({recap:.1f} vs {plain:.1f})")


def test_game_preview_is_weaker_than_recap():
    recap = _sc("Vikings beat Bears 24-17 on Sunday", team="Minnesota Vikings")
    preview = _sc("Vikings preview: what to watch against the Bears",
                  team="Minnesota Vikings")
    assert recap > preview
    print(f"  ok  recap outranks preview ({recap:.1f} vs {preview:.1f})")


def test_score_pattern_needs_game_context():
    """A 3-4 front and a 1-2 year deal are not final scores.

    Each used to collect the full W_GAME_RECAP bonus -- the biggest single
    weight in the scorer -- on the bare number pattern alone.
    """
    for title in ("Bears expected to run more 3-4 fronts this season",
                  "Bears agree to 1-2 year deal with veteran safety",
                  "Bears open 0-0 like everyone else"):
        fake = _sc(title)
        real = _sc("Bears beat Vikings 27-20", "Chicago improves to 1-0.")
        assert real > fake, f"{title!r} scored {fake} vs real recap {real}"
    print("  ok  3-4 fronts and 1-2 year deals are not final scores")


def test_undated_stories_still_decay():
    """Undated stories used to never fade and camped at the top."""
    story = {"title": "Bears place cornerback on injured reserve",
             "summary": "", "team": "Chicago Bears", "link": ""}
    undated = scoring.score_story(
        story, stats_for([story]), "Chicago Bears", NOW)[0]
    fresh = _sc("Bears place cornerback on injured reserve", hours_ago=2)
    assert undated < fresh, f"undated {undated} >= 2h-old {fresh}"
    print(f"  ok  undated stories decay ({undated:.1f} vs {fresh:.1f} fresh)")


def test_highlights_no_longer_penalised():
    """Game highlights are real content, not ceremonial filler."""
    hl = _sc("Highlights: Lions beat Bears 31-24 in Week 2",
             team="Detroit Lions")
    promo = _sc("Lions celebrate Girls Flag Football week in the community",
                team="Detroit Lions")
    assert hl > promo, f"highlights {hl} <= promo {promo}"
    print(f"  ok  highlights are content, not filler ({hl:.1f} vs {promo:.1f})")
'''


def check(text, edits):
    problems = []
    for label, find, _ in edits:
        n = text.count(find)
        status = "ok " if n == 1 else "BAD"
        print(f"   {status} {label:<34} anchor found {n}x")
        if n != 1:
            problems.append(label)
    return problems


def main():
    write = "--write" in sys.argv

    for p in (SCORING, TESTS):
        if not os.path.exists(p):
            print(f"ERROR: {p} not found. Run this from inside the repo.")
            return 1

    with open(SCORING, encoding="utf-8") as f:
        text = f.read()
    with open(TESTS, encoding="utf-8") as f:
        tests = f.read()

    print("Checking scoring.py anchors:")
    problems = check(text, EDITS)
    if problems:
        print()
        print("STOPPED -- nothing was changed.")
        print("These anchors did not match exactly once:")
        for p in problems:
            print(f"   {p}")
        print()
        print("That means scoring.py has already been patched, or it has")
        print("changed upstream. Send this output back rather than forcing it.")
        return 1

    already = "RECAP_DECAY_HALFLIFE_H" in text
    if already:
        print("\n   note: RECAP_DECAY_HALFLIFE_H already present -- already patched?")
        return 1

    for _, find, repl in EDITS:
        text = text.replace(find, repl)

    # The runner at the bottom of test_scoring.py collects test_* functions
    # out of globals() and calls them. Anything appended AFTER that block is
    # defined too late and never runs -- the file still reports ALL TESTS
    # PASSED, which is the worst possible failure mode for a test file. So
    # insert immediately BEFORE the runner.
    RUNNER = 'if __name__ == "__main__":'
    if "test_score_pattern_needs_game_context" in tests:
        print("\n   note: new tests already present -- skipping test append")
        new_tests = tests
    elif tests.count(RUNNER) != 1:
        print(f"\nSTOPPED -- expected exactly one runner block in "
              f"test_scoring.py, found {tests.count(RUNNER)}.")
        return 1
    else:
        head, _, tail = tests.partition(RUNNER)
        new_tests = head.rstrip("\n") + "\n" + NEW_TESTS + "\n\n" + RUNNER + tail

    # The new tests need timedelta.
    if "timedelta" not in new_tests.split("\ndef ")[0]:
        new_tests = new_tests.replace(
            "from datetime import datetime",
            "from datetime import datetime, timedelta", 1)

    if not write:
        print("\nAll anchors matched. Re-run with --write to apply:")
        print("   python apply_scoring_fixes.py --write")
        return 0

    shutil.copyfile(SCORING, SCORING + ".bak")
    shutil.copyfile(TESTS, TESTS + ".bak")
    with open(SCORING, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(TESTS, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_tests)

    print("\n   applied. Backups written to scoring.py.bak / test_scoring.py.bak")
    print("\nNow run the tests:")
    print("   python test_scoring.py")
    print("\nExpect 20 oks. If anything fails, restore with:")
    print("   copy scoring.py.bak scoring.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
