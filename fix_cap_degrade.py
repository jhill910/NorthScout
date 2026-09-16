"""Make the event cap degrade instead of taking the whole app down.

WHAT HAPPENED
-------------
On 2026-09-16 the live app died with:

    AttributeError: module 'scoring' has no attribute 'is_game_story'
      app.py line 216, in _cap_event_cluster

Streamlit Cloud had the new app.py but a cached older scoring module, so the
helper was missing. _cap_event_cluster guarded only against ImportError --
scoring imported fine, it just lacked the function -- and the AttributeError
propagated all the way out, blanking THE RUNDOWN and everything below it.

Losing the event cap is a minor degradation: the column shows more game
stories than ideal. Losing the entire dashboard mid-show-prep is not. The
rest of this project degrades rather than raises (standings keep the old
cache on a failed fetch, feeds skip rather than abort); this did not.

So: look the helper up with getattr, and if it is missing, return the frame
unchanged. A version skew between the two files now costs the cap, not the app.

    python fix_cap_degrade.py          # dry run
    python fix_cap_degrade.py --write
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")

OLD = '''    try:
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
'''

NEW = '''    try:
        import scoring
    except ImportError:
        return df

    # getattr, not scoring.is_game_story directly. On 2026-09-16 Streamlit
    # Cloud served the new app.py against a cached older scoring module; the
    # bare attribute access raised AttributeError, which the ImportError guard
    # above did not catch, and the whole dashboard went down. An uncapped
    # column is a small loss; a blank page during show prep is not.
    is_game = getattr(scoring, "is_game_story", None)
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
    return df.loc[keep + deferred]
'''


def main():
    write = "--write" in sys.argv
    if not os.path.exists(APP):
        print("ERROR: app.py not found. Run this from inside the repo.")
        return 1
    text = open(APP, encoding="utf-8").read()

    if 'is_game = getattr(scoring, "is_game_story", None)' in text:
        print("   note: already patched.")
        return 1

    n = text.count(OLD)
    print(f"Checking app.py:\n   {'ok ' if n == 1 else 'BAD'} cap guard   anchor found {n}x")
    if n != 1:
        print("\nSTOPPED -- nothing changed. Send this output back.")
        return 1

    if not write:
        print("\nAnchor matched. Re-run with --write to apply.")
        return 0

    shutil.copyfile(APP, APP + ".bak3")
    with open(APP, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(OLD, NEW))
    print("\n   applied. Backup: app.py.bak3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
