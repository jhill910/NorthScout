# NorthScout Diagnosis — Why the Show Doesn't Match the Site
**Date:** September 1, 2026
**Method:** Ran `agent.py`'s exact scoring algorithm against today's live team RSS feeds, then mapped the output against the 9/1 *1st and North* rundown.

---

## Headline finding

Of roughly **16 discussion beats** in today's rundown, the site would have surfaced **two** in usable form.

This is not a tuning problem. There are four independent failures, and each one alone would be enough to cause what you're seeing.

---

## Failure 1 — The ranking algorithm is mathematically guaranteed to bury news

`calculate_global_trends()` counts how often each word appears across every headline in the division. `get_top_team_news()` then scores each story by **summing the frequencies of the words it contains.**

Today's top "trending keywords" across all four feeds:

| word | count | word | count |
|---|---|---|---|
| bears | 67 | roster | 25 |
| packers | 58 | aug | 21 |
| camp | 38 | game | 18 |
| training | 36 | report | 18 |
| preseason | 29 | announce | 16 |

So "Bears **training camp report**: Thursday, Aug. 27" scores **215**, because every word in it is boilerplate that appears in dozens of other headlines.

Meanwhile the actual news — "Roster Moves: Chicago Bears agree to acquire fifth-round pick and DB Clark Phillips III in trade with Atlanta" — scores **139**, and lands at **#6**. One slot below your five-story cutoff.

**The mechanism: a story's score rises with how unremarkable its vocabulary is.** A scoop is by definition described in words no other article is using, so it scores near the floor. You built a consensus detector and are using it as a news detector.

Two secondary defects in the same function:
- `if word in title_lower` is a substring match, not a word match — "ram" matches "prog**ram**", "aug" matches "**aug**ment".
- Longer headlines score higher purely for containing more words. No length normalization.

### What the site would show today vs. what you actually discussed

**Chicago Bears** — 16 stories in window, 5 shown:

| # | score | headline shown |
|---|---|---|
| 1 | 215 | Bears training camp report: Joint practice with Titans \| Thursday, Aug. 27 |
| 2 | 191 | Bears training camp report: Tuesday, Aug. 25 |
| 3 | 190 | Bears training camp report: Wednesday, Aug. 26 |
| 4 | 180 | Bears training camp diaries with Sam Roush, Neville Gallimore \| Week 4 |
| 5 | 172 | How to watch, listen to, stream Bears-Titans Preseason Week 3 game |

Buried below the cutoff — **all of it on your rundown**:

| score | headline |
|---|---|
| 140 | Chicago Bears announce roster moves |
| 139 | Roster Moves: ...acquire fifth-round pick and DB Clark Phillips III in trade with Atlanta |
| 76 | **Ryan Poles talks roster cutdown day on preseason broadcast** ← dead last of 16 |

Your entire Segment 1 open — the Poles presser — was the **lowest-ranked Bears story on the board.**

**Green Bay Packers** — 49 stories in window, 5 shown: four *Live Look-In: Packers Training Camp* entries and a how-to-watch. Buried: Gutekunst on the roster (103), Kaleb Johnson (85), the Dolphins trade (79), the Rams trade (66).

**Detroit Lions** — shown: "Detroit vs. Detroit" camp culture, Campbell reflects on camp, Day 19 observations, Day 18 observations. Buried: 7 thoughts on the 53-man roster, the practice squad signings, the initial 53 breakdown.

**Minnesota Vikings** — the Walter Rouse trade to New England scored **14**, dead last.

---

## Failure 2 — Title-based dedupe silently deletes every transaction after the first

`database.py`:

```python
cursor.execute("SELECT id FROM team_news WHERE team = ? AND title = ?", (team, title))
if not cursor.fetchone():
    # insert
```

Teams publish **every** transaction under one recycled headline. Today's Bears feed contains **eight** separate stories titled exactly `Chicago Bears announce roster moves`. The Lions feed has two titled `Lions announce roster moves`.

Because dedupe keys on the title, only the **first one ever seen** is stored. Every subsequent one is discarded as a duplicate — permanently, since the check runs against the whole table with no date bound.

This is the bucket that contains:
- Braxton Jones winning the left tackle job; Jedrick Wills and Kiran Amegadjie cut
- The four Bears UDFAs (Jayden Loving, Hayden Large, Beau Gardner, Skylar Thomas)
- Greg Dortch's release
- Zavier Scott to the practice squad

**Every roster item in today's show lives inside a headline your database is configured to throw away.** Confirmed in your DB: 57 rows, 57 distinct titles — the dedupe is actively suppressing.

Compounding it: `clean_summary` truncates at 180 characters. Even the one roster-moves story that survives gets its transaction list cut off, so you can't see *who* was signed or cut without clicking through.

---

## Failure 3 — The computed ranking is discarded at display time

`agent.py` sorts by score and saves the top 5. Then `app.py`:

```sql
SELECT ... FROM team_news WHERE team = ? ORDER BY id DESC LIMIT 5
```

`ORDER BY id DESC` is **insertion order**, not score. There is no score column in the schema — the ranking is computed, used once to pick what to save, then thrown away. Your DB currently holds 14–15 rows per team and shows 5, selected by a different ordering than the one you calculated.

Net effect: two orderings fight each other, and the one that wins is "whatever got inserted most recently."

---

## Failure 4 — Structural blind spots no ranking fix can reach

Team-owned `.com` feeds are the club's PR arm. Some categories will never appear there at any ranking:

| Rundown item | Why it's invisible |
|---|---|
| **Josh Jacobs on the Commissioner's Exempt List, two misdemeanor charges** | packers.com will not publish a player's criminal charges. Zero coverage in any configured source. This was a full segment block. |
| **Kyler Gordon on PUP, calf, Poles: "I don't know"** | The transaction appears; the presser answer does not. No source for press-conference audio or transcripts. |
| **Brian Branch & Kerby Joseph opening on PUP** | Not in the Lions feed at all. |
| **Ben Johnson calling Caleb Williams "goofy"** | Presser quote. No source. |
| **J.J. McCarthy's roster status / who's QB2 on the first depth chart** | Speculative analysis. Not a PR product. |
| **Packers' 22-year UDFA streak (J. Michael Sturdivant)** | Contextual stat. Nothing in the feeds. |
| **Kwesi Adofo-Mensah's rookie hit rate / Nolan Teasley** | Beat-writer analysis. |
| **MLB's account throwing shade at the Packers (Cubs–Brewers)** | Outside the NFL entirely, and your X scrape is dead (see below). |

Every `==` break in your rundown is a SOT — a press conference clip. **Pressers are the spine of the show and the system has no source for them.** That's the single biggest content gap.

Related: `NFC_KEYWORDS` is a hardcoded 27-name list used to filter the national YouTube feeds. Kaleb Johnson, Clark Phillips, Gervon Dexter, Braxton Jones, Greg Dortch, Josh Jacobs, Brian Branch, Kerby Joseph and Sturdivant are all absent from it — so a McAfee or Herd segment about any of them is filtered out as irrelevant. The list needs to be derived from active rosters, not hand-maintained.

---

## Failure 5 — The sync didn't run, and X has never worked

**The refresh did not write.** `northscout.db` was last modified **June 29** and its newest story is from June 29. The live feeds are current through today — I verified all four return September 1 content. So the feeds are healthy; the write didn't happen.

Two likely causes, and I can't distinguish them from here:
1. **You refreshed the deployed Streamlit Cloud app, not this local copy.** Your git log has `fix: add production cloud migration failsafe for database columns`, and `northscout.db` is untracked. If the app is on Streamlit Community Cloud, its filesystem is ephemeral — the sync writes to a container that gets wiped on restart, and never touches this file.
2. **Working-directory mismatch.** Both `app.py` and `agent.py` open `sqlite3.connect("northscout.db")` as a *relative* path, while `app.py` goes to the trouble of resolving `sys.path` absolutely. Launch Streamlit from any other directory and it silently creates a second, empty database elsewhere.

Either way the fix is the same: resolve the DB path absolutely against `__file__`, and if you're on Cloud, move off SQLite-on-disk.

**X/Twitter has produced zero rows, ever.** `media_bites` holds 7 items, all YouTube, all from June 29. `twitter_auth.json` is a saved cookie jar from May 27 — those sessions expire in weeks. `scrape_x_media_bites()` detects the login wall, prints a warning, and `break`s. Since the sidebar button swallows all output, you never see it. That's why the MLB tweet wasn't available to you.

Also, your DB's `media_bites` table has **no `platform` column**, but `app.py` selects it. `init_db()`'s `ALTER TABLE` is wrapped in a bare `except sqlite3.OperationalError: pass`, which masks the failure.

---

## Recommended fixes, in order of impact

**1. Replace trend-scoring with editorial scoring.** Invert the current logic: rare, specific vocabulary should *raise* a story, not sink it. Score on signals that correlate with what the show discusses — transaction verbs (*sign, cut, waive, trade, claim, activate, place on*), status terms (*PUP, IR, exempt list, suspended*), named people, recency, and GM/coach attribution. Weight rarity **up** (TF-IDF style), not down.

**2. Stop deduping on title; dedupe on link.** One-line change with outsized effect — it immediately unlocks every roster-moves story. Also raise the summary truncation well above 180 characters for transaction posts, or store the full body, so you can see the actual names.

**3. Add a `score` column and sort by it in `app.py`.** Make the display honor the ranking you compute. Store everything in the window and rank at read time rather than pre-truncating to five in the scraper — that also lets you add a "show more" without re-scraping.

**4. Add non-PR sources.** This is what closes the Jacobs-shaped hole. All of these publish RSS: the SB Nation blogs (Windy City Gridiron, Pride of Detroit, Acme Packing Company, Daily Norseman), the metro papers (Tribune, Sun-Times, Free Press, Journal Sentinel, Star Tribune), ESPN's per-team feeds, and NFL.com. Add a league-wide transactions feed so the exempt-list and PUP moves arrive as first-class events.

**5. Add a presser/SOT source.** Team YouTube channels post full press conferences, usually within hours, and you're already parsing those feeds — you're just filtering them into the same undifferentiated "media bites" bucket. Detect press-conference uploads and surface them in their own rail with the speaker's name. This is the highest-value addition for how your show is actually built.

**6. Derive `NFC_KEYWORDS` from active rosters** rather than maintaining it by hand, so new signings and rookies are visible the day they arrive.

**7. Make failures loud.** Surface scrape results in the Streamlit UI — per-source counts, last-success timestamp, and an explicit red banner when the X session is expired. Right now every failure mode is a silent `print()` to a console you don't see. You should never again have to ask whether the refresh worked.

---

## Open question before I start

Is the site you refreshed running **locally** or on **Streamlit Cloud**? It changes fix #5 substantially — if it's Cloud, SQLite on the container filesystem can't persist between restarts regardless of what else we fix, and the storage layer needs to change.
