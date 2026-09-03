"""Live NFC North standings from ESPN's public API.

WHY THIS EXISTS
---------------
app.py used to render standings as hardcoded HTML: Bears 11-6-0, Packers
9-7-1, Vikings and Lions 9-8-0. Those were the 2025 final records, sitting
under a header reading "division standings" on a desk used during production.
Anyone glancing at it in September 2026 would read them as current.

Stale numbers presented as live are worse than no numbers, so this fetches the
real thing -- and when it can't, the dashboard says so rather than showing
something plausible and wrong.

PARSING NOTES
-------------
ESPN nests conferences -> divisions -> standings.entries. Rather than matching
on division-name strings (which change wording between seasons), this walks the
whole tree and picks out teams by ABBREVIATION. Missing or renamed stat fields
degrade to None instead of raising.

Run it directly to check it still works:

    python standings.py
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings"
TIMEOUT = 20
UA = "NorthScout/1.0 (NFC North show prep)"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STANDINGS_PATH = os.path.join(DATA_DIR, "standings.json")

# Abbreviation -> the team names used everywhere else in this project.
NFC_NORTH = {
    "CHI": "Chicago Bears",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "MIN": "Minnesota Vikings",
}

WANTED_STATS = ("wins", "losses", "ties", "pointDifferential",
                "streak", "playoffSeed", "divisionRecord")


def _fetch():
    try:
        req = urllib.request.Request(
            API_URL, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  standings: HTTP {e.code}")
    except Exception as e:
        print(f"   ⚠️  standings: {type(e).__name__}")
    return None


def _iter_entries(node):
    """Yield every standings entry anywhere in the tree."""
    if isinstance(node, dict):
        st = node.get("standings")
        if isinstance(st, dict):
            for e in st.get("entries") or []:
                yield e
        for child in node.get("children") or []:
            yield from _iter_entries(child)
        # Some responses put entries directly on the node.
        for e in node.get("entries") or []:
            yield e
    elif isinstance(node, list):
        for item in node:
            yield from _iter_entries(item)


def _stat(entry, name):
    for s in entry.get("stats") or []:
        if s.get("name") == name:
            v = s.get("value")
            if v is None:
                v = s.get("displayValue")
            return v
    return None


def parse(payload):
    """Return {team_name: {...}} for the four NFC North clubs."""
    out = {}
    if not payload:
        return out

    for entry in _iter_entries(payload):
        team = entry.get("team") or {}
        abbr = (team.get("abbreviation") or "").upper()
        if abbr not in NFC_NORTH:
            continue

        wins = _stat(entry, "wins")
        losses = _stat(entry, "losses")
        ties = _stat(entry, "ties")
        diff = _stat(entry, "pointDifferential")

        def _int(v):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None

        wins, losses, ties = _int(wins), _int(losses), _int(ties)
        diff = _int(diff)

        record = None
        if wins is not None and losses is not None:
            record = f"{wins}-{losses}" + (f"-{ties}" if ties else "")

        out[NFC_NORTH[abbr]] = {
            "abbr": abbr,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "record": record,
            "point_diff": diff,
            "streak": _stat(entry, "streak"),
            "division_record": _stat(entry, "divisionRecord"),
        }
    return out


def load_cached():
    if not os.path.exists(STANDINGS_PATH):
        return None
    try:
        with open(STANDINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def refresh():
    """Fetch, parse and cache. Returns the snapshot dict, or None on failure.

    Never overwrites a good cache with an empty result -- a transient network
    failure should not blank the standings block.
    """
    teams = parse(_fetch())
    if not teams:
        print("   ⚠️  standings: no NFC North teams parsed — keeping previous cache")
        return load_cached()

    snap = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ESPN",
        "teams": teams,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STANDINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"   ✅ standings: {len(teams)}/4 NFC North teams")
    return snap


if __name__ == "__main__":
    print("Checking ESPN standings API...\n")
    payload = _fetch()
    if payload is None:
        print("FAIL — no response. The endpoint may have moved.")
        raise SystemExit(1)

    print(f"  top-level keys: {list(payload.keys())}")
    teams = parse(payload)
    if not teams:
        print("\nFAIL — response received but no NFC North teams found.")
        print("  The shape has probably changed; fix standings.parse().")
        raise SystemExit(1)

    print(f"\n  parsed {len(teams)}/4 teams\n")
    print(f"  {'TEAM':<20} {'REC':>7} {'DIFF':>6}  STREAK")
    print("  " + "-" * 46)
    for name, t in teams.items():
        diff = t["point_diff"]
        diff_s = ("+" if diff and diff > 0 else "") + str(diff) if diff is not None else "—"
        print(f"  {name:<20} {t['record'] or '—':>7} {diff_s:>6}  {t['streak'] or '—'}")

    missing = [k for k in NFC_NORTH.values() if k not in teams]
    if missing:
        print(f"\n  WARNING: missing {missing}")
    print("\nStandings integration is working.")
