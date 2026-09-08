"""Editorial scoring for NorthScout.

WHY THIS REPLACES THE OLD SCORER
--------------------------------
The previous ranking summed, for each headline, how often its words appeared
across every other headline in the division. That made a story's score rise
with how *unremarkable* its vocabulary was. "Bears training camp report" scored
215 because every word in it is boilerplate; the Gervon Dexter trade scored 139;
the Ryan Poles cutdown-day presser scored 76, dead last of 16 Bears stories --
on the day it opened the show. A scoop is by definition described in words no
other article is using, so the old model mathematically guaranteed it sank.

This model scores what actually drives a football show, based on how the 9/1
rundown was built:

  timeliness            a presser today beats a camp note from Tuesday
  availability          who is playing, and who isn't
  transactions          signings, cuts, trades, claims, activations
  money at stake        contracts, guarantees, cap hits
  decision-maker voice  the GM or head coach on the record
  uncertainty           "I don't know" is a segment; "he looked good" is not
  narrative momentum    a name that has been in the news for days running
  distinctiveness       rare vocabulary now RAISES a story instead of sinking it

Every score carries its reasons, so the ranking can be audited rather than
trusted blindly.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import datetime

# --------------------------------------------------------------------------
# Weights. Tuned against the 2026-09-01 "1st and North" rundown; see
# tune_scoring.py for the measured effect of changes.
# --------------------------------------------------------------------------
W_RECENCY = 42.0          # max points for a brand-new story
RECENCY_HALFLIFE_H = 34.0 # hours until the recency bonus halves

W_AVAILABILITY = 26.0     # PUP / IR / exempt list / suspension / injury
W_TRANSACTION = 15.0      # signed, waived, traded, claimed, activated
W_MONEY = 14.0            # contract, extension, guaranteed, cap
W_ATTRIBUTION = 18.0      # named GM or head coach on the record
W_UNCERTAINTY = 20.0      # "I don't know", no timetable, won't say
W_CONFLICT = 24.0         # charges, arrest, investigation, holdout, dispute
W_MOMENTUM = 12.0         # entity has been in the news on multiple days
W_RARITY = 16.0           # distinctive vocabulary
W_DEPTH = 6.0             # substantive summary rather than a stub

P_BOILERPLATE = 30.0      # ceremonial / promotional / routine-recap content

# --------------------------------------------------------------------------
# Signal vocabularies
# --------------------------------------------------------------------------
AVAILABILITY = [
    "pup", "physically unable", "injured reserve", "reserve/injured", " ir ",
    "exempt list", "commissioner's exempt", "suspended", "suspension",
    "out for the season", "season-ending", "did not practice", "no timetable",
    "questionable", "doubtful", "designated to return", "non-football injury",
    "calf", "hamstring", "acl", "concussion", "torn", "surgery", "injury designation",
    # Everyday injury language the original list missed. "Bears' Rome Odunze,
    # D'Andre Swift hurt at practice" carried no availability signal at all
    # on 2026-09-08, despite being exactly the kind of story a producer needs.
    "hurt", "injured", "injury update", "limited participant", "full participant",
    "did not participate", "dnp", "missed practice", "left practice",
    "day-to-day", "week-to-week", "ruled out", "game-time decision",
    "activated off", "designated to return", "rehabbing", "setback",
]

TRANSACTION = [
    "signed", "signs", "sign", "waived", "waives", "waive", "released",
    "release", "cut", "cuts", "traded", "trade", "acquire", "acquired",
    "claimed", "claim", "activated", "activate", "placed on", "place on",
    "promoted", "elevated", "practice squad", "roster move", "roster moves",
    "53-man", "53 man", "cutdown", "waiver", "initial roster", "final roster",
    "roster decisions", "initial 2026 roster", "makes the roster", "depth chart",
]

# Calendar milestones the whole division reacts to in the same week. Setting
# the 53 or releasing the first depth chart is a major beat, not paperwork.
MILESTONE = [
    "53-man roster", "53 man roster", "initial roster", "initial 2026 roster",
    "final roster", "roster decisions", "roster limit", "cutdown", "depth chart",
]
W_MILESTONE = 11.0

# A player changing teams is a bigger deal than routine paperwork.
ACQUISITION = [
    "trade", "traded", "acquire", "acquired", "claimed off waivers",
    "new packers", "new bears", "new lions", "new vikings", "in exchange for",
]
W_ACQUISITION = 13.0

MONEY = [
    "contract", "extension", "guaranteed", "salary cap", "cap hit", "cap space",
    "million", "$", "franchise tag", "restructure", "holdout", "hold-in",
    "fined", "fine ", "incentive", "signing bonus", "deal ",
]

# Charitable and sponsorship money is not roster money. "Packers, Sargento
# teaming up to tackle hunger in Wisconsin" reached the Packers cards on
# 2026-09-08 flagged as "money: $, million" -- a donation, not a cap move.
CHARITY_MONEY = [
    "tackle hunger", "food bank", "fundraiser", "fundraising", "donation",
    "donates", "donated", "proceeds", "charity", "charitable", "teaming up",
    "partnership with", "raise money", "raised", "gives back", "toy drive",
    "scholarship", "grant", "non-profit", "nonprofit", "united way",
]

# Appearances and sightings. A GM watching a college game is not news, but he
# is a decision-maker, so attribution alone floated it to #2 on the Bears
# cards on 2026-09-08.
NON_EVENTS = [
    "in attendance", "attends", "attended", "spotted at", "was seen",
    "makes an appearance", "visits", "on hand for", "takes in",
    "guest of honor", "throws out", "honorary",
]

UNCERTAINTY = [
    "i don't know", "i dont know", "didn't know", "didn t know", "unclear",
    "uncertain", "no timetable", "won't say", "wouldn't say", "declined to say",
    "not sure", "up in the air", "remains to be seen", "question mark",
    "if he'll", "whether he", "unknown", "tbd", "no update",
]

CONFLICT = [
    "charged", "charges", "arrest", "arrested", "misdemeanor", "felony",
    "investigation", "allegation", "alleged", "lawsuit", "court", "exempt list",
    "dispute", "holdout", "trade request", "demanded", "benched", "fired",
    "stepping away", "controversy",
]

# HARD boilerplate: ceremonial, charitable and promotional pages. A producer
# never builds a segment on these, so they are damped multiplicatively --
# otherwise a community story published an hour ago rides the recency bonus
# straight into the top five.
HARD_BOILERPLATE = [
    "coach of the week", "high school", "flag football", "sweepstakes",
    "contest", "pep rally", "luncheon", "banquet", "hall of fame",
    "give back", "community", "university", "charity", "foundation",
    "donation", "youth", "classroom", "draft party", "watch party",
    "sign contest", "nominations", "anniversary", "trivia", "quiz",
    "girls", "volunteer", "scholarship", "food drive", "toy drive",
    # Sponsorship and charity partnerships. "Packers, Sargento teaming up to
    # tackle hunger in Wisconsin" held a card on 2026-09-08.
    "tackle hunger", "food bank", "fundraiser", "teaming up", "gives back",
    "proceeds", "donation", "donates", "non-profit", "nonprofit",
]

# Link paths are a reliable signal the club itself has filed a story as
# non-news -- e.g. /news/longform/ for career retrospectives.
HARD_BOILERPLATE_PATHS = ["/longform/", "/community/", "/youth/", "/fans/"]

# SOFT boilerplate: routine recaps and Q&A. Real content, low segment value.
BOILERPLATE = [
    "training camp report", "camp diaries", "live look-in", "how to watch",
    "how to listen", "tickets", "unveil", "uniform", "jersey", "game themes",
    "5 things to watch", "things to watch", "observations", "inbox",
    "mailbag", "lunchbreak", "photos", "gallery", "podcast", "celebrate",
    "honor", "behind the scenes", "look-in", "highlights",
    # Blog community formats. "Bears Over Beers Happy Hour and Open Thread:
    # Bears Trade Incoming?" ranked #1 on the live Bears board -- it is a
    # comment thread, not reporting.
    "open thread", "happy hour", "live chat", "game thread", "off-topic",
    "news and links", "links:", "daily links", "morning links", "survey",
    "poll:", "fan reaction", "reacts to", "over beers", "roundtable",
]

# Speech verbs -- an executive's name only counts as attribution if they are
# actually saying something, not merely being name-checked in a press release.
SPEECH = ["said", "says", "say", "talks", "talked", "told", "explained",
          "discussed", "addressed", "spoke", "speaking", "asked", "answered",
          "on why", "on how", "reacts", "confirmed", "announced"]

# Stories these people appear in carry the weight of the franchise's decisions.
DECISION_MAKERS = {
    "Chicago Bears": ["ryan poles", "ben johnson"],
    "Detroit Lions": ["brad holmes", "dan campbell"],
    "Green Bay Packers": ["brian gutekunst", "matt lafleur"],
    "Minnesota Vikings": ["kwesi adofo-mensah", "kevin o'connell", "kevin oconnell"],
}
ROLE_WORDS = ["general manager", "head coach", "gm ", " gm", "coordinator"]

STOPWORDS = {
    "the", "a", "an", "and", "in", "to", "for", "of", "on", "with", "at", "is",
    "as", "by", "from", "that", "this", "it", "his", "her", "their", "they",
    "was", "were", "be", "been", "has", "have", "had", "will", "would", "who",
    "what", "when", "how", "why", "not", "but", "or", "if", "we", "our", "you",
    "he", "she", "him", "them", "its", "are", "after", "before", "into", "out",
    "up", "down", "over", "about", "more", "most", "new", "first", "last",
    "nfl", "nfc", "north", "season", "week", "day", "game", "team", "teams",
}

TEAM_WORDS = {
    "bears", "lions", "packers", "vikings", "chicago", "detroit", "green",
    "bay", "minnesota", "minneapolis", "colts", "titans", "cardinals",
}

_WORD = re.compile(r"[a-z0-9'&.-]+")
# A run of capitalised words. Allow up to five so that "Packers RB Kaleb
# Johnson" is captured WHOLE and then trimmed -- the previous {1,2} limit
# matched only "Packers RB Kaleb", which was then thrown away for containing a
# team word, losing the player entirely.
_NAME = re.compile(r"\b([A-Z][a-zA-Z'\-\.]+(?: [A-Z][a-zA-Z'\-\.]+){1,4})\b")

# Positions and titles that prefix a name in club copy: "QB Kedon Slovis",
# "GM Brian Gutekunst", "TE Mark Redman".
POSITION_TOKENS = {
    "qb", "rb", "wr", "te", "ol", "dl", "lb", "db", "cb", "s", "k", "p", "ls",
    "g", "t", "c", "edge", "dt", "de", "fb", "ot", "og", "nt", "ilb", "olb",
    "fs", "ss", "gm", "ceo", "hc", "oc", "dc", "coach", "president", "owner",
    "rookie", "veteran", "all-pro", "pro",
}

# Every NFL club, so an opponent is never harvested as a person.
NFL_CLUBS = {
    "cardinals", "falcons", "ravens", "bills", "panthers", "bengals",
    "browns", "cowboys", "broncos", "texans", "colts", "jaguars", "chiefs",
    "raiders", "chargers", "rams", "dolphins", "patriots", "saints",
    "giants", "jets", "eagles", "steelers", "49ers", "niners", "seahawks",
    "buccaneers", "titans", "commanders", "arizona", "atlanta", "baltimore",
    "buffalo", "carolina", "cincinnati", "cleveland", "dallas", "denver",
    "houston", "indianapolis", "jacksonville", "kansas", "vegas",
    "angeles", "miami", "england", "orleans", "york", "philadelphia",
    "pittsburgh", "francisco", "seattle", "tampa", "tennessee", "washington",
    "indianapolis", "nashville",
}

# Words that disqualify a capitalised phrase from being a person's name.
# Without this, "Game Recap", "Man Roster" and "General Manager Brian" were
# being tracked as running storylines.
NAME_STOP = {
    "recap", "roster", "manager", "camp", "week", "day", "days", "practice",
    "squad", "preseason", "season", "game", "games", "notes", "report",
    "daily", "drive", "things", "takeaways", "observations", "inbox",
    "mailbag", "breakdown", "field", "stadium", "bowl", "draft", "news",
    "update", "updates", "highlights", "story", "stories", "list", "watch",
    "look", "review", "preview", "thoughts", "keys", "snap", "counts",
    "injury", "report", "depth", "chart", "moves", "move", "signing",
    "release", "trade", "deal", "contract", "team", "teams", "club",
    "coach", "coaching", "staff", "front", "office", "general",
}

NON_NAMES = {
    "Chicago Bears", "Detroit Lions", "Green Bay", "Green Bay Packers",
    "Minnesota Vikings", "New England", "Training Camp", "Roster Moves",
    "Practice Squad", "The Athletic", "Daily Drive", "Lions Daily",
    "Camp Notes", "How To", "Live Look", "Preseason Week", "Hall of Fame",
}


def tokens(text):
    return [w for w in _WORD.findall((text or "").lower())
            if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]


def _trim_name(tokens):
    """Strip leading club/position tokens and trailing club tokens.

    "Packers RB Kaleb Johnson" -> "Kaleb Johnson"
    "GM Brian Gutekunst"       -> "Brian Gutekunst"
    """
    def is_junk(tok):
        t = tok.lower().strip(".'-")
        return t in TEAM_WORDS or t in POSITION_TOKENS or t in NFL_CLUBS

    while tokens and is_junk(tokens[0]):
        tokens = tokens[1:]
    while tokens and is_junk(tokens[-1]):
        tokens = tokens[:-1]
    return tokens


def extract_names(text):
    out = set()
    for m in _NAME.finditer(text or ""):
        raw = m.group(1).strip()
        if raw in NON_NAMES:
            continue
        tokens = _trim_name(raw.split())
        if not 2 <= len(tokens) <= 3:
            continue
        n = " ".join(tokens)
        if n in NON_NAMES:
            continue
        low = n.lower()
        parts = [p.strip(".'-") for p in low.split()]
        if any(p in TEAM_WORDS or p in NFL_CLUBS for p in parts):
            continue
        if any(p in NAME_STOP for p in parts):
            continue
        out.add(n)
    return out


def parse_date(raw):
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw)[:len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def build_corpus_stats(stories):
    """Document frequencies for rarity, and per-entity day counts for momentum.

    `stories` is a list of dicts with title/summary/pub.
    """
    df = Counter()
    entity_days = defaultdict(set)
    per_team_docs = defaultdict(Counter)   # team -> name -> doc count
    team_totals = Counter()
    n_docs = 0

    for s in stories:
        n_docs += 1
        team = s.get("team", "_all")
        team_totals[team] += 1
        text = f"{s.get('title','')} {s.get('summary','')}"
        for w in set(tokens(text)):
            df[w] += 1
        dt = parse_date(s.get("pub") or s.get("fetched_at"))
        day = dt.date().isoformat() if dt else "unknown"
        for name in extract_names(text):
            entity_days[name].add(day)
            per_team_docs[team][name] += 1

    n_docs = max(n_docs, 1)

    # Beat reporters appear on most of their own team's stories, so they looked
    # like the division's hottest storyline -- "Tim Twentyman" was ranking the
    # Lions board. This must be measured PER TEAM: a Lions beat writer never
    # appears in Packers copy, so a corpus-wide threshold never caught him.
    staff = set()
    for team, counts in per_team_docs.items():
        total = max(team_totals[team], 1)
        for name, c in counts.items():
            if c >= max(3, 0.15 * total):
                staff.add(name)

    return {"df": df, "n_docs": n_docs, "entity_days": entity_days,
            "staff": staff}


_PAT_CACHE = {}


def _compile(needles):
    key = id(needles)
    if key not in _PAT_CACHE:
        parts = []
        for n in needles:
            n = n.strip()
            # \b doesn't work next to '$' or '/', so only bound alphanumerics
            lead = r"\b" if n[:1].isalnum() else ""
            tail = r"\b" if n[-1:].isalnum() else ""
            parts.append(f"{lead}{re.escape(n)}{tail}")
        _PAT_CACHE[key] = re.compile("|".join(parts))
    return _PAT_CACHE[key]


def _hits(haystack, needles):
    """Word-boundary matches. Naive substring matching made 'sign' fire on
    'Give Us a Sign Contest' and 'ir' fire on every word containing it."""
    return sorted(set(m.group(0).strip() for m in _compile(needles).finditer(haystack)))


def score_story(story, stats, team=None, now=None):
    """Return (score, reasons). Score is roughly 0-160; reasons explain it."""
    now = now or datetime.now()
    title = story.get("title", "") or ""
    summary = story.get("summary", "") or ""
    blob = f" {title.lower()} {summary.lower()} "

    score = 0.0
    reasons = []

    # --- timeliness -------------------------------------------------------
    dt = parse_date(story.get("pub") or story.get("fetched_at"))
    if dt:
        age_h = max((now - dt).total_seconds() / 3600.0, 0.0)
        rec = W_RECENCY * math.exp(-age_h / RECENCY_HALFLIFE_H)
        score += rec
        if rec >= 4:
            if age_h < 24:
                reasons.append(f"published {age_h:.0f}h ago")
            else:
                reasons.append(f"published {age_h/24:.1f}d ago")
    else:
        score += W_RECENCY * 0.3

    # --- availability -----------------------------------------------------
    av = _hits(blob, AVAILABILITY)
    if av:
        score += W_AVAILABILITY * min(len(av), 2) / 2
        reasons.append("availability: " + ", ".join(sorted(set(av))[:3]))

    # --- transactions -----------------------------------------------------
    tx = _hits(blob, TRANSACTION)
    if tx:
        score += W_TRANSACTION * min(len(tx), 3) / 3
        reasons.append("transaction: " + ", ".join(sorted(set(tx))[:3]))

    # --- roster-setting milestone -------------------------------------------
    ms = _hits(blob, MILESTONE)
    if ms:
        score += W_MILESTONE
        reasons.append("roster milestone: " + ", ".join(ms[:2]))

    # --- player changing teams ---------------------------------------------
    acq = _hits(blob, ACQUISITION)
    if acq:
        score += W_ACQUISITION
        reasons.append("acquisition: " + ", ".join(acq[:2]))

    # --- money ------------------------------------------------------------
    # Only roster money counts. Charity and sponsorship dollars are not a cap
    # move, however many dollar signs the headline carries.
    charity = _hits(blob, CHARITY_MONEY)
    mo = [] if charity else _hits(blob, MONEY)
    if mo:
        score += W_MONEY * min(len(mo), 2) / 2
        reasons.append("money: " + ", ".join(sorted(set(mo))[:2]))
    elif charity:
        reasons.append("charitable/sponsorship — not roster money")

    # --- decision-maker on the record -------------------------------------
    # A GM's name in a press release about a charity event is not attribution.
    # It only counts if they are on the record: named in the headline, or named
    # in the body alongside a speech verb.
    names = DECISION_MAKERS.get(team, [])
    title_l = title.lower()

    # An appearance is not a statement. "Bears GM Ryan Poles in attendance at
    # Miami-Stanford game" reached #2 on the Bears cards on 2026-09-08 purely
    # because a decision-maker was named in it.
    non_event = _hits(blob, NON_EVENTS)
    if non_event and not (av or ms or _hits(blob, CONFLICT)):
        score -= W_ATTRIBUTION * 0.8
        reasons.append("appearance, not news: " + ", ".join(non_event[:2]))
        names = []

    dm_title = [n for n in names if n in title_l]
    dm_body = [n for n in names if n in blob]
    speaking = bool(_hits(blob, SPEECH))
    if dm_title:
        score += W_ATTRIBUTION
        reasons.append("decision-maker on record: " + ", ".join(dm_title))
    elif dm_body and speaking:
        score += W_ATTRIBUTION * 0.8
        reasons.append("decision-maker quoted: " + ", ".join(dm_body))
    elif _hits(blob, ROLE_WORDS) and speaking:
        score += W_ATTRIBUTION * 0.45
        reasons.append("front-office/coaching voice")

    # --- uncertainty ------------------------------------------------------
    un = _hits(blob, UNCERTAINTY)
    if un:
        score += W_UNCERTAINTY
        reasons.append("uncertainty: " + ", ".join(sorted(set(un))[:2]))

    # --- conflict / off-field ---------------------------------------------
    cf = _hits(blob, CONFLICT)
    if cf:
        score += W_CONFLICT * min(len(cf), 2) / 2
        reasons.append("conflict: " + ", ".join(sorted(set(cf))[:2]))

    # --- narrative momentum ----------------------------------------------
    ent_days = stats["entity_days"]
    staff = stats.get("staff", set())
    best_name, best_days = None, 0
    for name in extract_names(f"{title} {summary}"):
        if name in staff:
            continue
        d = len(ent_days.get(name, ()))
        if d > best_days:
            best_name, best_days = name, d
    if best_days >= 2:
        score += W_MOMENTUM * min(best_days - 1, 3) / 3
        reasons.append(f"running storyline: {best_name} ({best_days} days)")

    # --- distinctiveness (IDF) -------------------------------------------
    df, n_docs = stats["df"], stats["n_docs"]
    toks = [t for t in set(tokens(title)) if t not in TEAM_WORDS]
    # log(1) == 0, so a single-document corpus would divide by zero. That is a
    # real path: a feed can return one story, or every other feed can fail.
    if toks and n_docs > 1:
        idf = sum(math.log(n_docs / (1 + df.get(t, 0))) for t in toks) / len(toks)
        denom = math.log(n_docs)
        norm = max(0.0, min(idf / denom, 1.0)) if denom > 0 else 0.0
        score += W_RARITY * norm
        if norm > 0.6:
            reasons.append("distinctive wording")

    # --- substance --------------------------------------------------------
    if len(summary) > 120:
        score += W_DEPTH
    elif not summary:
        score -= W_DEPTH * 0.5

    # --- soft boilerplate: routine recaps and Q&A -------------------------
    bp = _hits(blob, BOILERPLATE)
    if bp:
        pen = P_BOILERPLATE * min(len(bp), 3) / 3
        if dm_title or cf or av:
            pen *= 0.4
        score -= pen
        reasons.append("routine: " + ", ".join(bp[:3]))

    # --- hard boilerplate: ceremonial content ------------------------------
    # Damped multiplicatively, not subtracted, so that a charity story filed an
    # hour ago cannot ride the recency bonus into the top five. Genuine
    # off-field news (an arrest, a suspension) is exempt.
    link = (story.get("link") or "").lower()
    hard = _hits(blob, HARD_BOILERPLATE)
    hard_path = [p for p in HARD_BOILERPLATE_PATHS if p in link]
    if (hard or hard_path) and not cf:
        score *= 0.25
        label = ", ".join((hard + hard_path)[:3])
        reasons = [f"ceremonial/promotional ({label}) — heavily damped"]

    return round(max(score, 0.0), 2), reasons
