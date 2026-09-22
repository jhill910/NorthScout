"""Add a pre-taping scrape run.

THE PROBLEM
-----------
1st and North tapes Tuesdays at roughly 2:30pm CT. The scrape ran at 6am CT
and 4pm CT -- so the afternoon run landed ninety minutes AFTER the show was
already recorded, and nothing ran during the eight and a half hours in
between. Every Tuesday the board was at least half a day old at taping.

On 2026-09-22 the snapshot was built 10:28 CT against a 2:30pm CT taping:
four hours stale. The broadcast opened with Tyson Bagent entering concussion
protocol, which broke minutes before taping and was never going to be there.

THE FIX
-------
A run at 18:45 UTC (1:45pm CT) puts a fresh board in front of producers
forty-five minutes before they walk in. Daily rather than Tuesday-only: it
costs nothing, and a weekday-shaped cron is one more thing to get wrong.

The 4pm CT run stays -- it still catches afternoon transactions for the next
day's prep.

FOR GENUINELY LATE NEWS
-----------------------
Nothing scheduled can catch a post made two minutes before taping. For that,
trigger the workflow by hand: GitHub -> Actions -> the scrape workflow ->
"Run workflow". It takes a couple of minutes, then reload the dashboard.
That path already exists (workflow_dispatch) and is worth knowing.

    python fix_scrape_schedule.py          # dry run
    python fix_scrape_schedule.py --write
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, ".github", "workflows", "scrape.yml")

OLD = '''    # 11:00 UTC = 6am CT, 21:00 UTC = 4pm CT.
    # Morning run has overnight news ready before show prep; afternoon run
    # catches same-day pressers, cuts and transactions.
    - cron: "0 11 * * *"
    - cron: "0 21 * * *"
'''

NEW = '''    # 11:00 UTC = 6am CT, 18:45 UTC = 1:45pm CT, 21:00 UTC = 4pm CT.
    #
    # The 1:45pm run exists because the show tapes around 2:30pm CT. Before
    # it was added the schedule jumped from 6am straight to 4pm -- ninety
    # minutes AFTER taping -- so producers always worked from a board that
    # was at least half a day old. On 2026-09-22 it was four hours stale and
    # the broadcast opened with news that broke after the snapshot was built.
    #
    # Nothing scheduled catches news that breaks minutes before air. For
    # that, trigger this workflow by hand from the Actions tab.
    - cron: "0 11 * * *"
    - cron: "45 18 * * *"
    - cron: "0 21 * * *"
'''


def main():
    write = "--write" in sys.argv
    if not os.path.exists(WF):
        print(f"ERROR: {WF} not found.")
        return 1
    text = open(WF, encoding="utf-8").read()
    if '45 18 * * *' in text:
        print("   note: pre-taping run already present.")
        return 1
    n = text.count(OLD)
    print(f"Checking scrape.yml:\n   {'ok ' if n == 1 else 'BAD'} cron block   anchor found {n}x")
    if n != 1:
        print("\nSTOPPED -- nothing changed. Send this output back.")
        return 1
    if not write:
        print("\nAnchor matched. Re-run with --write to apply.")
        return 0
    shutil.copyfile(WF, WF + ".bak")
    with open(WF, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(OLD, NEW))
    print("\n   applied. Backup: .github/workflows/scrape.yml.bak")
    print("   Commit and push -- GitHub picks up the new schedule automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
