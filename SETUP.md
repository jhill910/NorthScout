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

---

## Still open

These came out of the diagnosis and are **not** fixed yet:

1. **The ranking algorithm still rewards boilerplate.** It scores a headline by summing how often its words appear elsewhere, so "Bears training camp report" beats a trade. Your 9/1 Poles presser ranked dead last of 16 Bears stories. Storing everything with scores means nothing is lost anymore, but the *order* is still wrong. This is the next big win.
2. **No press-conference source.** Every `==` break in your rundown is a SOT, and nothing in the pipeline captures pressers. Team YouTube channels post them within hours.
3. **Team PR feeds can't cover off-field news.** The Josh Jacobs exempt-list story was structurally unreachable. Needs beat blogs, metro papers, and a league transactions feed.
4. **`NFC_KEYWORDS` is a hand-maintained list of 27 names.** Kaleb Johnson, Clark Phillips, Gervon Dexter, Braxton Jones and Josh Jacobs are all missing, so national clips about them get filtered out as irrelevant.

See `DIAGNOSIS_2026-09-01.md` for the full analysis.
