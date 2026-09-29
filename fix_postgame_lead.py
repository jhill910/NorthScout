"""Let postgame content lead the day after a game.

WHAT WAS WRONG (2026-09-29, the morning after Bears-Eagles on MNF)
------------------------------------------------------------------
The Bears column led with a CBS roundup, put a PREVIEW of the game that had
already been played at #3, and filled slots 4-8 with a Dolphins story, two
sportsbook promo ads, a power-rankings post and an MVP-race post. The actual
postgame press conference -- "Ben Johnson on Bears' victory over Eagles",
carrying SOT -- sat at position 258.

Three separate causes, two of them introduced by the event cap added a week
earlier and never tested against a Monday night game:

1. THE PERSON CAP ATE THE PRESSER. _diversify allows two stories per person.
   The day after a game the head coach is in every headline by definition --
   four of the top five Bears stories named Ben Johnson -- so the 3rd and 4th
   were deferred, and one of them was the press conference. A person cap
   cannot tell crowding from coverage when the person IS the coverage.
   Press conferences are primary source and are now exempt.

2. A STALE PREVIEW TOOK A GAME SLOT. _cap_event_cluster kept the top three
   "game" stories without distinguishing a recap from a preview, so a
   pre-game writeup of a finished game consumed a slot that belonged to
   postgame material. Recaps and previews now have separate budgets.

3. SPORTSBOOK PROMOS SCORED LIKE NEWS. "Use DraftKings promo code to claim
   $150 in bonus bets" scored 72.0 and held a Bears card. Added to
   HARD_BOILERPLATE, which already damps to 0.25 -- reusing the tested path
   rather than inventing a second one. Deliberately NOT damped: "odds",
   "opening lines", "spread". Opening lines are editorially useful; a
   sign-up bonus is an advertisement.

MEASURED AFTER: Bears presser 258 -> 4. Campbell's postgame to Lions #3.
O'Connell on the J.J. McCarthy trade leads Minnesota. Promos off the board.

    python fix_postgame_lead.py          # dry run
    python fix_postgame_lead.py --write
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCORING = os.path.join(HERE, "scoring.py")
APP = os.path.join(HERE, "app.py")

SCORING_EDITS = [(
    "sportsbook promos as boilerplate",
    '''    "tackle hunger", "food bank", "fundraiser", "teaming up", "gives back",
    "proceeds", "donation", "donates", "non-profit", "nonprofit",
]
''',
    '''    "tackle hunger", "food bank", "fundraiser", "teaming up", "gives back",
    "proceeds", "donation", "donates", "non-profit", "nonprofit",
    # Sportsbook advertising. "Use DraftKings promo code to claim $150 in
    # bonus bets" scored 72.0 and held a Bears card on 2026-09-29, directly
    # below the Monday night win. These are adverts wearing a headline.
    #
    # NOT listed, deliberately: "odds", "opening lines", "spread". An
    # opening line is a real editorial item -- the show cites them -- while
    # a sign-up bonus is not. The distinction is the offer, not the betting.
    "promo code", "bonus code", "bonus bets", "sign-up offer", "signup offer",
    "odds boost", "first bet offer", "welcome offer", "use code",
]
'''
), (
    "presser and game-kind helpers",
    '''def is_game_story(title, summary=""):''',
    '''def is_press_conference(title, summary=""):
    """True if this is a press conference or media availability.

    Producers build segments from what the head coach actually said, so a
    presser is primary source rather than another take. app.py exempts these
    from the per-person cap: the day after a game the coach appears in every
    headline, and a cap that cannot tell crowding from coverage buried the
    Bears postgame presser at position 258 on 2026-09-29.
    """
    blob = f" {str(title).lower()} {str(summary).lower()} "
    return ("press conference" in blob
            or "media availability" in blob
            or "postgame availability" in blob
            or "\\U0001F3A4" in str(title))


def game_story_kind(title, summary=""):
    """'recap', 'preview' or None.

    is_game_story() answers "is this about a game" but not "which game, and
    has it happened yet". A preview of a game already played is worthless the
    morning after, and one held a slot that belonged to postgame coverage.
    """
    blob = f" {str(title).lower()} {str(summary).lower()} "
    if _hits(blob, GAME_RECAP):
        return "recap"
    if _hits(blob, GAME_PREVIEW):
        return "preview"
    return "recap" if is_game_story(title, summary) else None


def is_game_story(title, summary=""):'''
)]

APP_EDITS = [(
    "exempt pressers from the person cap",
    '''    clusters, keep, deferred = {}, [], []
    for idx, row in df.iterrows():
        title_l = str(row.get("title", "")).lower()''',
    '''    clusters, keep, deferred = {}, [], []
    for idx, row in df.iterrows():
        # Press conferences bypass the person cap. The day after a game the
        # head coach is in every headline, so the cap deferred the Bears
        # postgame presser to position 258 on 2026-09-29. A presser is
        # primary source -- the coach being named is definitional, not
        # crowding.
        _presser = getattr(scoring, "is_press_conference", None)
        if callable(_presser):
            try:
                if _presser(row.get("title", ""), row.get("summary", "")):
                    keep.append(idx)
                    continue
            except Exception:
                pass
        title_l = str(row.get("title", "")).lower()'''
), (
    "separate recap and preview budgets",
    '''    is_game = getattr(scoring, "is_game_story", None)
    if not callable(is_game):
        return df

    keep, deferred, n = [], [], 0
    for idx, row in df.iterrows():
        try:
            game = is_game(row.get("title", ""), row.get("summary", ""))
        except Exception:
            # A malformed row should drop out of the cap, not out of the board.
            game = False
        if game:
            if n >= max_game:
                deferred.append(idx)
                continue
            n += 1
        keep.append(idx)
    return df.loc[keep + deferred]''',
    '''    kind_of = getattr(scoring, "game_story_kind", None)
    if not callable(kind_of):
        return df

    # Recaps and previews get separate budgets. Sharing one budget let a
    # preview of an ALREADY PLAYED game take a slot on 2026-09-29, pushing
    # the postgame press conference and snap-count analysis off the board.
    # One preview slot is kept because the show's closing segment is all
    # look-aheads.
    limits = {"recap": max_game, "preview": 1}
    counts = {"recap": 0, "preview": 0}

    keep, deferred = [], []
    for idx, row in df.iterrows():
        try:
            k = kind_of(row.get("title", ""), row.get("summary", ""))
        except Exception:
            # A malformed row should drop out of the cap, not out of the board.
            k = None
        if k in limits:
            if counts[k] >= limits[k]:
                deferred.append(idx)
                continue
            counts[k] += 1
        keep.append(idx)
    return df.loc[keep + deferred]'''
)]


def run(path, edits, label, text):
    print(f"\nChecking {label}:")
    bad = []
    for name, find, _ in edits:
        n = text.count(find)
        print(f"   {'ok ' if n == 1 else 'BAD'} {name:<34} anchor found {n}x")
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
    stext = open(SCORING, encoding="utf-8").read()
    atext = open(APP, encoding="utf-8").read()
    if "def is_press_conference" in stext:
        print("   note: already patched.")
        return 1

    new_s, bad1 = run(SCORING, SCORING_EDITS, "scoring.py", stext)
    new_a, bad2 = run(APP, APP_EDITS, "app.py", atext)
    if bad1 or bad2:
        print("\nSTOPPED -- nothing changed. Send this output back.")
        return 1
    if not write:
        print("\nAll anchors matched. Re-run with --write to apply.")
        return 0

    shutil.copyfile(SCORING, SCORING + ".bak4")
    shutil.copyfile(APP, APP + ".bak4")
    with open(SCORING, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_s)
    with open(APP, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_a)
    print("\n   applied. Backups: scoring.py.bak4 / app.py.bak4")
    print("\n   python test_scoring.py")
    print("   python -m streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
