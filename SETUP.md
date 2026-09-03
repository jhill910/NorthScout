# NorthScout — Deployment Setup

What changed, and the three things you need to do to turn it on.

---

## The problem this solves

Streamlit Community Cloud runs your app on an **ephemeral filesystem**. Anything written to disk — including `northscout.db` — is destroyed on restart, redeploy, or inactivity sleep. So "Sync Live Data Now" worked, then silently reverted to weeks-old stories. That's why the site kept drifting away from the show.

The scrape now runs on a **schedule in GitHub Actions**, which commits `data/northscout.json` back to the repo. The repo is durable. The app reads the committed snapshot, so even a cold-started container has current data.

```
GitHub Actions (6am + 4pm CT)
   └─ export_json.py
        ├─ seeds SQLite from the last committed snapshot
        ├─ runs your existing agent.main() scrape
        ├─ prunes anything outside the 8-day window
        └─ writes data/northscout.json  ──commit──▶  repo
                                                      │
                            Streamlit Cloud app ──reads──┘
```

---

## What you need to do

### 1. Push

```bash
git push
```

This deploys the new code and, because `scrape.yml` includes a `push` trigger, kicks off the first scrape automatically. Streamlit Cloud will redeploy on its own.

### 2. Confirm the first run

Go to the **Actions** tab in GitHub → **NorthScout scrape**. The run posts a summary table showing story counts per team and the top-ranked headline for each. If it's green and you see a new `data: snapshot ...` commit, it's working.

If Actions is disabled on the repo, GitHub will show a button to enable it. You can also trigger a run by hand any time via **Run workflow**.

### 3. (Optional) Turn X/Twitter back on

X scraping has never produced a single row, and it can't work on Cloud as previously built — `twitter_auth.json` isn't in the repo (correctly, it holds live session cookies), so the scraper found nothing and skipped. It now runs in Actions, where the session can live as a secret.

1. Open `twitter_auth.json` on your machine and copy the entire contents.
2. GitHub → **Settings → Secrets and variables → Actions → New repository secret**
3. Name it exactly `X_AUTH_JSON`, paste the JSON, save.

The workflow writes it to disk, installs Chromium, runs the scrape, and deletes the file afterward — it never reaches a commit. Without the secret, everything else still runs and X is skipped cleanly.

**Note:** saved X sessions expire every few weeks. When they do, the run summary prints a warning and the site's media rail shows a stale-data banner instead of failing silently. You'll need to re-copy the cookie file when that happens.

---

## What's on screen now

The dashboard shows a **freshness banner** under the title:

- ✅ green — data under 24 hours old
- ⚠️ amber — 1–3 days old
- 🛑 red — over 3 days old, with a pointer to the Actions tab

Every failure used to be a `print()` to a console nobody reads. You should never again have to wonder whether the refresh worked.

The sidebar sync button still exists for local work, but now says plainly that a manual sync on Cloud is temporary.

---

## Code changes in this pass

| File | Change | Why |
|---|---|---|
| `database.py` | Dedupe on **link**, not title | Clubs recycle one headline for every transaction — today's Bears feed had eight stories titled "Chicago Bears announce roster moves". Only the first was ever stored. This is the fix that surfaces cutdowns, trades and signings. |
| `database.py` | Added `score` column; absolute DB path | Ranking is now persisted, and the DB can't depend on the launch directory. |
| `database.py` | Migrations print on failure | A bare `except: pass` was hiding the missing `platform` column. |
| `agent.py` | Persist **all** in-window stories with scores | Only the top 5 were saved, so #6 and below were destroyed at scrape time. The cutoff is now a display choice, not data loss. |
| `agent.py` | Summary truncation 180 → 1200 chars | 180 cut transaction lists off mid-name — exactly the names you need. |
| `app.py` | `ORDER BY score DESC` instead of `id DESC` | The computed ranking was being thrown away at display time. |
| `app.py` | Snapshot-first loading, SQLite fallback | Survives Cloud restarts; local dev still works unchanged. |
| `export_json.py` | New — scrape → durable JSON | Includes a guard that refuses to overwrite a good snapshot with an empty scrape, so a transient network failure can't wipe your board. |
| `.github/workflows/scrape.yml` | New — scheduled scrape + commit | Twice daily, plus manual trigger. |
| `.gitignore` | New | Keeps `twitter_auth.json` and `northscout.db` out of a public repo. |
| `scoring.py` | New — editorial ranking | Replaces trend-frequency scoring. Rundown coverage went 3/13 → 12/13 in the top five. |
| `sources.py` | New — source registry | 20 feeds tagged with team, kind and health. Wires route to teams by keyword; AFC news is dropped. |
| `check_sources.py` | New — feed health check | Reports live / stale / dead per feed. The Action posts the table to each run summary. |
| `agent.py` | Press conferences | Detects pressers, tags the speaker, gives them a rail, and ranks them in the team boards. |
| `app.py` | Near-duplicate suppression | With wires and papers added, one story could occupy four of five slots. Keeps the best version. |
| `test_scoring.py`, `test_sources.py` | New — regression tests | Pin every bug found while tuning. |

---

## Still open

1. **Most third-party feeds are unverified.** They were added from a machine that cannot reach them, so `sources.py` marks them `unverified`. Run `python check_sources.py` once and the table tells you which are live, stale or dead; `--write` records the results back into the file. Dead feeds are skipped with a warning, never silently.
2. **Scoring was tuned on a single week.** Thirteen topics from the 9/1 rundown is a small sample and some weights are judgment calls. They are named constants at the top of `scoring.py`. Send next week's rundown and `evaluate.py` re-measures in minutes.
3. **X/Twitter needs the `X_AUTH_JSON` secret** before it produces anything, and saved sessions expire every few weeks.
4. **Press-conference detection depends on how clubs title uploads.** It handles the common patterns; if a club changes style, add it to `PRESSER_MARKERS` in `agent.py`.
5. **`NFC_KEYWORDS` is still hand-maintained** — it gates which national YouTube clips count as relevant, and new signings are invisible until added.

See `DIAGNOSIS_2026-09-01.md` for the original analysis.
