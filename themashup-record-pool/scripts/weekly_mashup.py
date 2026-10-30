#!/Library/Frameworks/Python.framework/Versions/3.10/bin/python3
"""Weekly Mashup job (Percy, 20 Oct 2026). Runs Thursday evening (launchd com.percy.mashup-weekly).

Takes, in priority order, up to CAP downloads a week (never anything blocked / deleted / already pulled):
  1. Beatport Top 20 (current week): chart tracks Percy doesn't have — 'missing' and 'near'
  2. Tom Barker: everything uploaded since the last run (both versions where there are two)
  3. Remixers: new uploads by every remixer in rekordbox's `Remixers` folder (37 on 20 Oct 2026),
     plus the remixers and artists Percy follows in ~/opt/record-pools/mashup/follow.txt (30 Oct 2026)
  4. New releases in his genre groups: House/Club, Disco/Soul/Funk, R&B/Urban, Throwback/Party
  5. Tom Barker backlog: older edits he doesn't have, newest first, with whatever is left of the cap
Then: tag_fill → ~/Downloads (the ingest imports them) → Beatport playlist waiter → summary on the
Desktop + notification + audit entry. Also writes ~/opt/record-pools/mashup/remixers.txt for the Xtendamix weekly.

  weekly_mashup.py            dry run: print the plan
  weekly_mashup.py --apply    download and hand over
"""
import json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmu
from rekordbox_check import core_title, norm, artist_agrees, load_library, BLOCKLIST

APPLY = "--apply" in sys.argv
CAP = 60
TB_BACKLOG = 25
STATE = os.path.expanduser("~/opt/record-pools/mashup/weekly_state.json")
REMIXERS_FILE = os.path.expanduser("~/opt/record-pools/mashup/remixers.txt")
FOLLOW_FILE = os.path.expanduser("~/opt/record-pools/mashup/follow.txt")   # "remixer: Name" / "artist: Name" lines
RUNS = os.path.expanduser("~/opt/record-pools/mashup/runs")
SUMMARY = os.path.expanduser("~/Desktop/Mashup_weekly.txt")
PY = "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3"
AUDIT = os.path.expanduser("~/opt/home-audit/audit.sh")
EMAIL = os.path.expanduser("~/opt/record-pools/pool-email.sh")      # mails Percy through Jenkins
# Mashup type pages (/site/filtertype/<id>, newest first, 75 a page), grouped as Percy chose
GROUPS = {
    "House/Club": [6, 8, 5, 7, 4, 22, 67, 3],          # House, Tech, Disco, Piano, Funky House, Garage, Soulful, Deep
    "Disco/Soul/Funk": [38, 37, 58, 43, 23],           # Disco, Soul, Funk, Motown, Club Classic
    "R&B/Urban": [9, 32, 1],                           # R&B, Hip Hop, Dancehall/Reggae
    "Throwback/Party": [24, 10],                       # Throwback, Pop & Party (70s-00s only, see below)
}
OLD_DECADES = {"70's", "80's", "90's", "00's"}
SKIP_TYPES = {"Acapella", "Instrumental", "FX", "Producer Countdown"}
SKIP_GENRES = {"Acapellas", "Instrumentals", "Acapella Intros", "Acapella Outros"}
# genre feed only: the Mashup posts each new song in several house edits; take the main mix, skip these
EDIT_GENRES = {"Short Edits", "Transitions", "TMU Toilet Break Mix", "Hype Intros", "Wordplays", "Halloween",
               "Party/Freshers", "Radio Edits", "Strings"}
MIX_RANK = [r"extended mix", r"original mix|orignal mix", r"club mix", r"\bremix\b", r"radio edit"]


def mix_rank(track):
    t = track.lower()
    return next((i for i, p in enumerate(MIX_RANK) if re.search(p, t)), len(MIX_RANK)) + (0 if "(clean)" in t else 0.5)


def up_date(r):
    try:
        return datetime.strptime(r["uploaded"], "%d %b %Y")
    except (ValueError, KeyError):
        return datetime(1970, 1, 1)


def follows(kind):
    """Names Percy follows beyond the Remixers folder: lines 'remixer: Name' or 'artist: Name' in FOLLOW_FILE."""
    if not os.path.exists(FOLLOW_FILE):
        return []
    rows = [l.split(":", 1) for l in open(FOLLOW_FILE) if ":" in l and not l.lstrip().startswith("#")]
    return [n.strip() for k, n in rows if k.strip().lower() == kind and n.strip()]


def remixers():
    """Names of the folders under rekordbox's top-level `Remixers` folder (read-only; rekordbox may be open)."""
    try:
        from pyrekordbox import Rekordbox6Database
        db = Rekordbox6Database(db_dir="/Volumes/MUSIC/.PIONEER/Master")
        f = next(p for p in db.get_playlist() if p.Name == "Remixers" and p.Parent is None)
        names = sorted(ch.Name for ch in f.Children if int(ch.Attribute or 0) == 1)
        db.close()
        if names:
            open(REMIXERS_FILE, "w").write("\n".join(names) + "\n")
            return names
    except Exception as e:
        print("could not read Remixers folder, using the saved list:", e)
    return [l.strip() for l in open(REMIXERS_FILE)] if os.path.exists(REMIXERS_FILE) else []


def email(subject, body):
    if APPLY:
        subprocess.run([EMAIL, subject], input=body, text=True)


def main():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {"last_run": "2026-10-14", "runs": []}
    since = datetime.strptime(st["last_run"], "%Y-%m-%d") - timedelta(days=1)     # 1 day overlap
    stamp = datetime.now().strftime("%Y-%m-%d")
    s = tmu.session()
    acct = tmu.status(s)
    if not acct["logged_in"]:
        msg = "Mashup session expired - log in at themashup.co.uk in the Playwright browser"
        os.system(f"osascript -e 'display notification \"{msg}\" with title \"Mashup weekly\"'")
        open(SUMMARY, "w").write(f"Mashup weekly {stamp}: NOT RUN - {msg}\n")
        if APPLY:
            subprocess.run([AUDIT, "MUSIC", "DOWNLOADS", "BLOCKED", "Mashup weekly job could not log in", msg, f"mashup-weekly-{stamp}"])
        email(f"Mashup weekly {stamp}: NOT RUN, login expired", msg + "\n")
        sys.exit(1)

    lib = load_library()
    blocked = {l.split("\t")[0].strip() for l in open(BLOCKLIST) if l.strip() and not l.startswith("#")} \
        if os.path.exists(BLOCKLIST) else set()

    def status(r, need=None):
        if r["id"] in blocked or r["downloaded"]:
            return "skip"
        ents = lib.get(core_title(r["track"]), [])
        if need:
            hit = [e for e in ents if need.lower() in (e[0] + " " + e[2]).lower()]
        else:
            hit = [e for e in ents if artist_agrees(r["artist"], e[1])]
        return "have" if hit else ("near" if ents else "missing")

    picked, ids = [], set()

    songs = set()      # (artist, core title) already picked, so a song comes once across all sources

    def take(rows, why, need=None, keep_versions=False, statuses=("missing", "near"), feed=False):
        """add new candidates. Outside Tom Barker: one version per song (Clean, then Extended > Original > ...);
        feed=True (genre pages) also skips the extra house edits."""
        out = []
        for r in rows:
            if r["id"] in ids or status(r, need) not in statuses:
                continue
            if set(r.get("types", [])) & SKIP_TYPES or set(r.get("genres", [])) & SKIP_GENRES:
                continue
            if feed and re.search(r"[\u0590-\u06ff\u0400-\u04ff\u3040-\u30ff\u4e00-\u9fff]", r["artist"] + r["track"]):
                continue                      # Hebrew / Arabic / Cyrillic / CJK titles: not Percy's crowd
            if feed and (set(r.get("genres", [])) & EDIT_GENRES or re.search(r"halloween|tmu .*edit|transition", r["track"], re.I)):
                continue
            out.append(r)
        if not keep_versions:
            best = {}
            for r in out:
                k = (norm(r["artist"]), core_title(r["track"]))
                if k in songs:
                    continue
                if k not in best or mix_rank(r["track"]) < mix_rank(best[k]["track"]):
                    best[k] = r
            out = list(best.values())
            songs.update(best)
        out = [dict(r, why=why) for r in out]
        for r in out:
            ids.add(r["id"]); picked.append(r)
        return out

    # 1. Beatport Top 20, current week
    ch = tmu.chart(s, "beatport-top-20")
    newest = ch["archived_weeks"][0] if ch["archived_weeks"] else stamp
    wk = datetime.strptime(newest, "%Y-%m-%d") + timedelta(days=7)
    bp_name = f"Beatport Top 20 wk {wk.day} {wk:%b %Y}"
    bp = take(ch["rows"], "Beatport Top 20")

    # 2. Tom Barker, new since the last run (both versions)
    tb_all = [r for r in tmu.producer(s, "tombarker") if "tom barker" in r["track"].lower()]
    tb_new = take([r for r in tb_all if up_date(r) >= since], "Tom Barker new", need="Tom Barker", keep_versions=True)

    # 3. remixers in rekordbox's Remixers folder
    rmx = []
    folder = remixers()
    for name in folder + [n for n in follows("remixer") if n.lower() not in {f.lower() for f in folder}]:
        if name.lower() == "tom barker":
            continue
        rows = [r for r in tmu.search(s, name) if name.lower() in r["track"].lower() and up_date(r) >= since]
        rmx += take(rows, f"Remixer: {name}", need=name)
        time.sleep(0.5)
    # 3b. artists Percy follows: their new uploads, one version per song, no mashups / seasonal edits
    for name in follows("artist"):
        rows = [r for r in tmu.search(s, "", name) if name.lower() in r["artist"].lower() and up_date(r) >= since
                and not re.search(r"mashup|halloween|christmas|xmas|transition|toilet break", r["track"], re.I)]
        rmx += take(rows, f"Artist: {name}")
        time.sleep(0.5)

    # 4. genre groups: this week's uploads, then shared out round-robin so no group crowds the others out
    by_group = {}
    for g, types in GROUPS.items():
        gen = []
        for t in types:
            rows, off = [], 0
            while off <= 600:
                page = tmu.parse_rows(s.get(f"{tmu.BASE}/site/filtertype/{t}" + (f"/{off}" if off else "")).text)
                rows += [r for r in page if up_date(r) >= since]
                if len(page) < 75 or up_date(page[-1]) < since:
                    break
                off += 75; time.sleep(0.5)
            if g == "Throwback/Party":
                rows = [r for r in rows if 24 == t or set(r.get("types", [])) & OLD_DECADES]
            gen += take(rows, f"New: {g}", feed=True)
            time.sleep(0.5)
        by_group[g] = gen
    gen = []
    while any(by_group.values()):
        for g in GROUPS:
            if by_group[g]:
                gen.append(by_group[g].pop(0))

    # 5. Tom Barker backlog, newest first
    backlog = take(sorted(tb_all, key=up_date, reverse=True), "Tom Barker backlog", need="Tom Barker", keep_versions=True)

    # cap, in priority order; the backlog gets at most TB_BACKLOG of what's left
    order = bp + tb_new + rmx + gen
    chosen = order[:CAP]
    chosen += backlog[:max(0, min(TB_BACKLOG, CAP - len(chosen)))]
    deferred = [r for r in order[CAP:]]

    lines = [f"Mashup weekly {stamp}  (uploads since {since:%d %b})  -  {len(chosen)} to download, cap {CAP}",
             f"credits before: {acct['downloads_remaining']} monthly + {acct['bolton_remaining']} bolt-on", ""]
    for why in dict.fromkeys(r["why"].split(":")[0] for r in chosen):
        grp = [r for r in chosen if r["why"].split(":")[0] == why]
        lines.append(f"{why} ({len(grp)}):")
        lines += [f"   {r['artist']} - {r['track']}" + (f"   [{r['why'].split(': ',1)[1]}]" if ": " in r["why"] else "") for r in grp]
    if deferred:
        lines += ["", f"Over the cap, left for next week ({len(deferred)}):"] + [f"   {r['artist']} - {r['track']}  [{r['why']}]" for r in deferred[:40]]
    print("\n".join(lines))
    if not APPLY:
        print("\ndry run - re-run with --apply"); return

    run = os.path.join(RUNS, f"weekly_{stamp}")
    os.makedirs(run, exist_ok=True)
    json.dump(chosen, open(os.path.join(run, "checked.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(ch["rows"], open(os.path.join(run, "beatport_rows.json"), "w"), ensure_ascii=False)
    with open(os.path.join(run, "beatport_checked.json"), "w") as f:      # library matches for the playlist builder
        subprocess.run([PY, os.path.join(HERE, "rekordbox_check.py"), os.path.join(run, "beatport_rows.json")], stdout=f)
    res = tmu.download(s, [r["id"] for r in chosen], run)
    ok = [r for r in res["results"] if r["ok"]]
    subprocess.run([PY, os.path.join(HERE, "tag_fill.py"), os.path.join(run, "checked.json"), res["manifest"], "--dir", run])
    dest = os.path.expanduser(f"~/Downloads/_tmu_weekly_{stamp}")
    os.makedirs(dest, exist_ok=True)
    for r in ok:
        shutil.copy2(os.path.join(run, r["file"]), dest)
    if ch["rows"]:
        subprocess.Popen(["nohup", os.path.join(HERE, "rekordbox_chart_playlist_wait.sh"),
                          os.path.join(run, "beatport_checked.json"), res["manifest"], bp_name],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    after = tmu.status(s)
    fails = [r for r in res["results"] if not r["ok"]]
    lines += ["", f"downloaded {len(ok)}, failed {len(fails)}; credits now {after['downloads_remaining']} monthly + "
              f"{after['bolton_remaining']} bolt-on", f"files: {run}", f"playlist '{bp_name}' builds when rekordbox is next closed"]
    open(SUMMARY, "w").write("\n".join(lines) + "\n")
    st["last_run"] = stamp
    st["runs"].append({"date": stamp, "chosen": len(chosen), "ok": len(ok), "failed": len(fails), "deferred": len(deferred)})
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)
    subprocess.run([AUDIT, "MUSIC", "DOWNLOADS", "DONE" if not fails else "FAILED",
                    f"Mashup weekly job: downloaded {len(ok)} tracks (Beatport, Tom Barker, remixers, new releases)",
                    f"{len(fails)} failed; {len(deferred)} over the cap; summary {SUMMARY}", f"mashup-weekly-{stamp}"])
    email(f"Mashup weekly {stamp}: {len(ok)} downloaded" + (f", {len(fails)} FAILED" if fails else ""), "\n".join(lines) + "\n")
    os.system(f"osascript -e 'display notification \"{len(ok)} new tracks downloaded - see Mashup_weekly.txt on the Desktop\" with title \"Mashup weekly\"'")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        email(f"Mashup weekly {datetime.now():%Y-%m-%d}: FAILED with an error", traceback.format_exc())
        raise
