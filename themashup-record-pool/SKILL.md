---
name: themashup-record-pool
description: Use when Percy wants tracks from themashup.co.uk (his DJ record pool) — searching it, filling the basket, downloading a chart or a producer's edits (Tom Barker, Beatport Top 20), skipping what rekordbox already has, or getting those downloads tagged and into a rekordbox playlist.
---

# themashup.co.uk record pool

## Overview

Everything on the site is plain HTTP once you hold the login cookie, so drive it with
`scripts/tmu.py` rather than clicking in a browser. Downloads are metered (200/month +
bolt-on), so **list → cross-check against rekordbox → confirm with Percy → download**.

## Getting a session

1. The site needs a password; you never type it. Percy logs in himself in the
   Playwright browser (`mcp__playwright__browser_navigate` to
   `https://themashup.co.uk/login`). That browser is its own Chrome profile, so his normal
   Chrome login does not carry over. The Claude-in-Chrome extension has not connected on
   this Mac; go straight to Playwright.
2. Capture the cookie with `mcp__playwright__browser_run_code_unsafe`:
   `async (page) => (await page.context().cookies('https://themashup.co.uk')).map(c=>c.name+'='+c.value).join('; ')`
   and save it to `~/.config/themashup_cookie.txt` (mode 600). Only `tmusession` matters.
3. `python3 scripts/tmu.py status` → `logged_in`, downloads remaining, basket size.
   The cookie file persists; try `status` before asking Percy to log in again.

## Workflow

| Step | Command |
|---|---|
| Find tracks | `tmu.py search "title" ["artist"]` — max 75 rows, no paging; add the artist to narrow |
| Whole producer catalogue | `tmu.py producer tombarker` (slug from `/site/producertracks/<slug>`) — pages through all |
| Weekly chart | `tmu.py chart beatport-top-20 [YYYY-MM-DD]` — "Top 20" page actually lists 50; archives weekly |
| What Percy has | `rekordbox_check.py rows.json [--require-in-title "Tom Barker"]` — read-only, rekordbox may stay open |
| Basket | `tmu.py basket` / `basket-add ID…` / `basket-remove ID…` — **capped at 75 items**; adds rejected at the cap are moved by the site into the **wishlist** (`tmu.py wishlist`), so check both before re-adding |
| Download | `tmu.py download ID… --out DIR` — 320k MP3 named `Artist - Title.mp3` + `manifest.tsv` |
| Into rekordbox | copy the MP3s to `~/Downloads`; after 20 s run `~/bin/ingest_downloads.py` (moves them to `/Volumes/MUSIC/MusicCollection`, queues import) |
| Fill missing tags | `tag_fill.py checked.json manifest.tsv` — year (MusicBrainz, else upload year), BPM, key |
| Chart playlist | `nohup rekordbox_chart_playlist_wait.sh checked.json manifest.tsv "Beatport Top 20 wk 17 Sep 2026" &` — builds folder + playlist once rekordbox is closed and the import queue is empty |

Row fields: `id uid track artist bpm key genres types uploaded downloaded in_basket`.
`producer` and `chart` rows come newest-upload first, so "the next N" = the first N candidates
in that order. Chart playlists are named `<chart> wk <D Mon YYYY>` where the date is the
newest `archived_weeks` entry plus 7 days (the current week is not in the archive list); the
folder is the chart's name ("Beatport").
`downloaded=true` (greyed on the site) means Percy already pulled it; re-downloading costs a
credit and the site refuses after two.

## Weekly job (installed, automatic)

`scripts/weekly_mashup.py --apply` runs on **Thursday from 19:00**, once per ISO week. It is
started by `~/bin/auto_flush.sh`, not by its own launchd agent: only that script's children can
read the MUSIC SSD (TCC). Percy agreed the policy on 20 Oct 2026, including downloading without
asking each week.
- **Cap:** 60 downloads a week (raised from 45 on 20 Oct 2026), taken in this order:
  1. Beatport Top 20 'missing' and 'near' tracks;
  2. new Tom Barker edits (both versions);
  3. new uploads by every remixer in rekordbox's `Remixers` folder, plus the remixers and artists in
     `~/opt/record-pools/mashup/follow.txt` (`remixer: Name` / `artist: Name` lines; added 30 Oct 2026:
     Anthem Kingz, Low Steppa, David Guetta, Joel Corry — artists skip mashups and seasonal edits);
  4. new releases in four groups (House/Club, Disco/Soul/Funk, R&B/Urban, Throwback/Party),
     shared out round-robin, one main mix per song, extra edits skipped;
  5. the Tom Barker backlog, up to 25 a week from whatever is left.
- **"New"** means uploaded since the last run, with one day of overlap. State is in
  `~/opt/record-pools/mashup/weekly_state.json`.
- **Outputs:**
  - files in `~/opt/record-pools/mashup/runs/weekly_<date>/`, copied to `~/Downloads`;
  - the `Beatport Top 20 wk <date>` playlist waiter;
  - `~/Desktop/Mashup_weekly.txt`, a notification and an audit entry;
  - an email with the summary (also on a crash or expired login), via
    `~/opt/record-pools/pool-email.sh`, which asks Jenkins' `Reporting/Pool Job Email` job to send it;
  - the log in `~/opt/record-pools/mashup_weekly.log` (written unbuffered, `python3 -u`).
- **Watchdog:** `~/opt/record-pools/watchdog.sh`, run from `auto_flush.sh`, emails once if the job
  hasn't reported by 23:00 Thursday (hung, never started, or died, as in the 23 Oct 2026 power cut).
- **Dry run:** `weekly_mashup.py` with no flag prints the plan.
- **Remixer list:** the job writes the names to `~/opt/record-pools/mashup/remixers.txt` for the Xtendamix
  weekly.

The genre groups' type ids (`GROUPS` in the script) come from probing `/site/filtertype/1..89`:
for example 6 House, 8 Tech House, 9 R&B, 24 Throwback, 38 Disco. Type pages list newest first,
75 to a page, paged by `/site/filtertype/<id>/<offset>`. The `/site/genre/<name>` pages show no
rows; they only link to sub-genres.
A producer slug that doesn't exist (for example `drpacker`) seems to page through the whole site:
it returned 5,025 rows. Find remixers by name with `search` instead.

## Rules that came from doing it wrong

- **Deleted means deleted.** A track the site marks `downloaded` that is no longer in the
  library was removed by Percy on purpose. `rekordbox_check.py` marks it `deleted`, appends
  it to `~/opt/record-pools/mashup/never_download.txt`, and reports it as `blocked` from then on. Never
  download `deleted` or `blocked` rows, and never "restore" one because it looks like a
  chart gap. Percy edits that file to unblock.
- **Confirm before downloading or basket-adding en masse.** Report counts and the
  candidate list first; Percy decides. Basket adds are free and reversible; downloads are not.
- **"Not in my collection" for a producer's edits means that producer's edit is missing**,
  not the song. Use `--require-in-title "Tom Barker"`; also report how many of the
  candidates Percy has in another version so he can trim.
- **A remix is a different track.** The cross-check calls ARTBAT & Guetta's 2026 remix of
  *Somebody That I Used To Know* "have" because Gotye matches. Read the `lib` matches.
- **`near` = same title, other/unknown artist.** Treat as missing, but say so.
- **Never write the rekordbox DB while rekordbox is running** (corruption history). The
  waiter script enforces this; the flush/auto-flush already imports the files.
- The ingest **skips files younger than 15 s** and archives originals to
  `~/Downloads/_music_added`; tag the collection copies, not the archive.
- Site tags arrive with title/artist/genre/artwork and album "TheMashup.co.uk" but **no year,
  BPM or key** — always run `tag_fill.py`. The importer copies title/artist/genre only; the
  playlist script copies the file year into the DB as well.
- `tag_fill.py` also stamps a `COMM` comment frame (`desc="source"`, text `themashup.co.uk`)
  on every file it touches, so a track's pool of origin is visible in its tags later. Guarded
  by desc, so re-running never duplicates it even alongside other comment frames (iTunes'
  own `iTunNORM`/`iTunSMPB` etc.).
- **Do not read the Playwright browser's network log or snapshot for lists** — it is 75 KB a
  page. Use the script.
- **The basket keeps already-downloaded rows** (greyed, `class='downloaded'`), so Percy's UI badge
  counts them: 9 "staged" on 2 Oct 2026 was 8 spent + 1 genuinely new. Check `downloaded` before
  reporting what is staged, and clear spent rows with `basket-remove` when he asks.
- **`basket_process process=delete` can refuse with the bare reply `twice`** and silently not
  delete — seen on a track that had been downloaded twice (the site's two-download ceiling).
  Retrying does nothing; it is server-side. Leave it and tell Percy to remove it in the UI.
- **Arming more than one playlist waiter is safe now, but only because of a lock.** Every waiter
  fires the instant rekordbox quits, so two armed batches used to mean two processes writing
  master.db at once — the June 2026 corruption route. `rekordbox_chart_playlist_wait.sh` takes an
  atomic `mkdir` lock at `/Volumes/MUSIC/.scan/.playlist_build.lock` and the second one waits its
  turn. Also: never edit the waiter while instances are running (bash re-reads the file) — kill
  them and re-arm.
- **`downloads_remaining` does not decrement 1:1 and cannot be taken literally.** 2 Oct 2026: 23
  remaining → 21 downloads → 12 remaining; and the account page showed 228 used against a stated
  200/month limit while still offering 12. The counter that IS reliable is "Downloads in current
  period" (it moved exactly +21) and the bolt-on balance. Quote Percy the used count and bolt-ons,
  and treat "remaining" as indicative.
- **Credits**: `status` reports two separate pots — `downloads_remaining` is the **monthly plan**
  (200/month, resets on its own date) and `bolton_remaining` is a **standing balance of extra
  downloads bought on top**, which does not reset monthly and needs an active subscription to
  spend. The account page (`/site/myaccount`) is the authoritative wording.
- **`producer` paging was silently truncating to one page** (fixed 2 Oct 2026). It stopped when
  the page's "N Tracks" text looked satisfied, which for `tombarker` read as 75 — so a 900-track
  catalogue appeared to be 75 rows with only 6 undownloaded. It now pages until a short page and
  dedupes by id. **Sanity-check any producer result against what Percy already holds**: 900 rows
  / 379 downloaded matched his library's `Remixers > Tom Barker` count exactly, which is what
  confirmed the fix. A row count that is an exact multiple of 75 is a red flag.

## Endpoints (for when the script needs fixing)

POST `/site/search` (`searchtrackname`, `searchtrackartist`, `advsearch=0`) ·
`/site/producertracks/<slug>/<offset>` (75/page) · `/site/trending/<slug>[/<week>]` ·
POST `/site/basket_process` (`process=add|delete`, `tid`, `uid`; returns basket count or
"Maximum number…") · POST `/site/wishlist` (`process=wishadd|wishdelete`, `tid`, `uid`) ·
`/site/wishlisttracks/<wishlist id>` (rows) · GET `/site/download/<id>` → `application/octet-stream` with
`Content-Disposition` filename · POST `/site/get_downloads_remaining`.
Rows are `tr[data-id]`; class `downloaded` = already pulled; `button.playme` carries
`data-track/artist/bpm`; `.tmupill` "Key: 5A / C Minor".
