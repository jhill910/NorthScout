"""Source registry for NorthScout.

WHY A REGISTRY
--------------
The old scraper hardcoded five URLs, four of which were team-owned .com feeds.
Team sites are the club's PR arm: they publish transactions and camp notes, but
they will never publish a player's criminal charges, an honest injury outlook,
or a beat writer's read on who is actually starting. On 2026-09-01 the Josh
Jacobs commissioner's-exempt-list story -- a full segment block -- was
structurally unreachable from every configured source.

This registry adds non-PR outlets and, critically, records which ones are
KNOWN GOOD versus UNVERIFIED, so a dead feed shows up as a warning rather than
quietly narrowing the board.

Run `python check_sources.py` to test every feed and print a health table.
Feeds that fail are skipped at scrape time with a logged warning; they never
break the run.

STATUS values
    "verified"   fetched successfully and returned dated items
    "unverified" plausible but not yet confirmed from this machine
    "disabled"   known broken or intentionally switched off
"""

# Every entry: (label, url, team, kind, status)
#   team  -- one of the four clubs, or "division" for league-wide wires
#   kind  -- "official" | "blog" | "paper" | "wire"
#
# "official" feeds are PR. They are reliable and fast on transactions, but the
# scoring engine should never be asked to find controversy in them.

SOURCES = [
    # ---------------- Official club feeds (verified 2026-09-01) -------------
    ("Bears.com",   "https://www.chicagobears.com/rss/news",  "Chicago Bears",     "official", "verified"),
    ("Lions.com",   "https://www.detroitlions.com/rss/news",  "Detroit Lions",     "official", "verified"),
    ("Packers.com", "https://www.packers.com/rss/news",       "Green Bay Packers", "official", "verified"),
    ("Vikings.com", "https://www.vikings.com/rss/news",       "Minnesota Vikings", "official", "verified"),

    # ---------------- League-wide wires -----------------------------------
    # These are the ones that carry exempt-list moves, suspensions, arrests and
    # trades before (or instead of) the clubs. Stories are routed to a team by
    # keyword match in agent.py, and dropped if they mention no NFC North club.
    ("ProFootballTalk", "https://profootballtalk.nbcsports.com/feed/", "division", "wire", "verified"),
    ("NFL.com",         "https://www.nfl.com/feeds/rss/news",          "division", "wire", "disabled"),
    ("ESPN NFL",        "https://www.espn.com/espn/rss/nfl/news",      "division", "wire", "disabled"),
    ("CBS Sports NFL",  "https://www.cbssports.com/rss/headlines/nfl/","division", "wire", "verified"),
    ("Yahoo NFL",       "https://sports.yahoo.com/nfl/rss.xml",        "division", "wire", "verified"),

    # ---------------- SB Nation team blogs --------------------------------
    ("Windy City Gridiron",  "https://www.windycitygridiron.com/rss/current.xml",   "Chicago Bears",     "blog", "verified"),
    ("Pride of Detroit",     "https://www.prideofdetroit.com/rss/current.xml",      "Detroit Lions",     "blog", "verified"),
    ("Acme Packing Company", "https://www.acmepackingcompany.com/rss/current.xml",  "Green Bay Packers", "blog", "verified"),
    ("Daily Norseman",       "https://www.dailynorseman.com/rss/current.xml",       "Minnesota Vikings", "blog", "verified"),

    # Already in the original config.
    ("Sports Mockery", "https://sportsmockery.com/category/bears/feed", "Chicago Bears", "blog", "disabled"),

    # ---------------- Metro papers ----------------------------------------
    # Closest to what the reporters on the show actually read. Several are
    # paywalled -- the RSS headline and summary are still useful for spotting a
    # story even when the body isn't readable.
    ("Chicago Tribune Bears",   "https://www.chicagotribune.com/sports/bears/feed/",         "Chicago Bears",     "paper", "disabled"),
    ("Chicago Sun-Times Bears", "https://chicago.suntimes.com/bears/rss.xml",                "Chicago Bears",     "paper", "verified"),
    ("Detroit Free Press",      "https://www.freep.com/rss/sports/lions/",                   "Detroit Lions",     "paper", "disabled"),
    ("Detroit News Lions",      "https://www.detroitnews.com/rss/sports/nfl/lions/",         "Detroit Lions",     "paper", "disabled"),
    ("Milwaukee Journal Sentinel", "https://www.jsonline.com/rss/sports/packers/",           "Green Bay Packers", "paper", "disabled"),
    ("Star Tribune Vikings",    "https://www.startribune.com/vikings/index.rss2",            "Minnesota Vikings", "paper", "disabled"),
]


# Wire stories mention every club in the league, so they need routing.
#
# CLUB terms only -- cities, nicknames, venues. These never change.
#
# PLAYER names are deliberately NOT hardcoded here. A hand-typed roster goes
# stale exactly when a player moves, and on 2026-09-08 that put "Cowboys'
# captains: Kenny Clark, Quinnen Williams, Dak Prescott..." on the Packers
# board, because Clark was still listed under Green Bay after moving to
# Dallas. People come from roster.py, which learns them from the feeds.
#
# Coaches and GMs stay: they change rarely, and they anchor a story to a club
# more reliably than any player.
TEAM_ROUTING = {
    "Chicago Bears": [
        "bears", "chicago bears", "halas hall", "soldier field",
        "ryan poles", "ben johnson",
    ],
    "Detroit Lions": [
        "lions", "detroit lions", "ford field", "allen park",
        "dan campbell", "brad holmes",
    ],
    "Green Bay Packers": [
        "packers", "green bay", "lambeau", "lambeau field",
        "matt lafleur", "brian gutekunst",
    ],
    "Minnesota Vikings": [
        "vikings", "minnesota vikings", "u.s. bank stadium", "us bank stadium",
        "kevin o'connell", "kevin oconnell", "kwesi adofo-mensah",
    ],
}

# Every other NFL club. If one of these owns the headline, the story belongs to
# them -- however many NFC North players happen to be named in it.
OTHER_CLUBS = [
    "cardinals", "falcons", "ravens", "bills", "panthers", "bengals",
    "browns", "cowboys", "broncos", "texans", "colts", "jaguars", "chiefs",
    "raiders", "chargers", "rams", "dolphins", "patriots", "saints",
    "giants", "jets", "eagles", "steelers", "49ers", "niners", "seahawks",
    "buccaneers", "titans", "commanders",
]


def active_sources(include_unverified=True):
    """Feeds to attempt this run."""
    out = []
    for label, url, team, kind, status in SOURCES:
        if status == "disabled":
            continue
        if status == "unverified" and not include_unverified:
            continue
        out.append({"label": label, "url": url, "team": team,
                    "kind": kind, "status": status})
    return out


import re
import re as _re

_ROUTE_CACHE = {}


def _club_pattern(keys):
    """Word-boundary matcher for a club's terms.

    Naive substring matching routed 'NFL legend Emmitt Smith accused of
    scamming a company out of millions' to the Detroit Lions, because
    'lions' is inside 'mil-LIONS'. Observed live on 2026-09-03.
    """
    key = tuple(keys)
    if key not in _ROUTE_CACHE:
        parts = [r"\b" + _re.escape(k) + r"\b" for k in keys]
        _ROUTE_CACHE[key] = _re.compile("|".join(parts))
    return _ROUTE_CACHE[key]


def route_to_teams(title, summary="", roster_names=None):
    """Which NFC North clubs is this story actually ABOUT?

    Three rules, every one of them learned from a live misroute:

    1. Word boundaries, not substrings. 'millions' is not the Lions.
    2. A single passing mention in the body is not enough. A Rams schedule
       piece naming the Packers once landed on the Packers board. The club
       must appear in the HEADLINE, or at least twice in the body.
    3. If ANOTHER NFL club owns the headline, the story is theirs. "Cowboys'
       captains: Kenny Clark, Quinnen Williams, Dak Prescott" reached Green
       Bay purely because Clark used to play there. When a rival club is named
       in the headline, an NFC North CLUB term must also be in the headline --
       a player name alone won't do it, because players move.

    roster_names: optional {team: {lowercased names}} from roster.py. Used
    only to strengthen a match, never as the sole basis when a rival club owns
    the headline.
    """
    title_l = (title or "").lower()
    body_l = (summary or "").lower()

    rival_owns_headline = bool(_club_pattern(OTHER_CLUBS).search(title_l))

    hits = []
    for team, keys in TEAM_ROUTING.items():
        pat = _club_pattern(keys)
        club_in_title = bool(pat.search(title_l))

        if rival_owns_headline:
            # Only a genuine club reference rescues it.
            if club_in_title:
                hits.append(team)
            continue

        if club_in_title or len(pat.findall(body_l)) >= 2:
            hits.append(team)
            continue

        # No club term, but a current player of theirs is named in the
        # headline. Roster is harvested from the feeds, so it stays current.
        if roster_names:
            names = roster_names.get(team) or set()
            if names and any(re.search(r"\b" + re.escape(n) + r"\b", title_l)
                             for n in names if len(n) > 6):
                hits.append(team)
    return hits


def mark_status(label, status):
    """Rewrite this file's STATUS for a feed. Used by check_sources.py --write."""
    import os
    import re

    path = os.path.abspath(__file__)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = re.compile(
        r'(\("' + re.escape(label) + r'",\s*"[^"]+",\s*"[^"]+",\s*"[^"]+",\s*")'
        r'(verified|unverified|disabled)(")'
    )
    new_text, n = pattern.subn(lambda m: m.group(1) + status + m.group(3), text)
 