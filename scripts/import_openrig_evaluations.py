#!/usr/bin/env python3
"""One-off: import the songs analyzed under OpenRig into the tone library.

Reads `<source>/<eval>/eval.md` (title `# <Song> — <Artist>`) and
`<source>/<eval>/refs/*`, and writes only into the library root. Each guitar
reference is copied into the library with its audio and re-analyzed with the
current analyzer; `original.*` becomes the song's track (harmonics are read on it).

    .venv/bin/python scripts/import_openrig_evaluations.py [--root tones] [--dry-run] [--jobs 4] SOURCE...
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tone_analyzer import _common, tones

AUDIO = {".wav", ".mp3", ".flac", ".aiff", ".aif"}
NOT_GUITAR = {"keys", "vocals", "vocal", "bass", "drums", "piano", "other", "no-guitar"}
ROLE_PREFERENCE = ["lead", "rhythm", "acoustic", "clean"]
TITLE = re.compile(r"^#\s*(?P<song>.+?)\s+—\s+(?P<artist>.+?)\s*$")


def _title(eval_dir: Path) -> tuple[str, str] | None:
    md = eval_dir / "eval.md"
    if not md.is_file():
        return None
    m = TITLE.match(md.read_text(encoding="utf-8").splitlines()[0] if md.stat().st_size else "")
    return (m["artist"], m["song"]) if m else None


def _role_rank(role: str) -> int:
    return ROLE_PREFERENCE.index(role) if role in ROLE_PREFERENCE else len(ROLE_PREFERENCE)


def plan(sources: list[Path]) -> tuple[list[dict], list[str]]:
    evals = []
    for src in sources:
        for d in sorted(p for p in Path(src).expanduser().iterdir() if p.is_dir() and not p.name.startswith("_")):
            refs = sorted(f for f in (d / "refs").glob("*") if f.suffix.lower() in AUDIO) if (d / "refs").is_dir() else []
            track = next((f for f in refs if f.stem == "original"), None)
            guitar = []
            skipped_here = []
            for f in refs:
                if f is track:
                    continue
                role = "-".join(re.findall(r"[a-z0-9]+", f.stem.lower()))
                if role in NOT_GUITAR:
                    skipped_here.append(f"{d.name}/{f.name}: not a guitar reference")
                    continue
                guitar.append({"role": role, "file": f, "sha": _common.sha256_file(f)})
            guitar.sort(key=lambda g: (_role_rank(g["role"]), g["role"]))
            evals.append({"dir": d, "title": _title(d), "track": track, "refs": guitar, "skipped": skipped_here})

    titled_shas = {g["sha"] for e in evals if e["title"] for g in e["refs"]}
    jobs, skipped, seen, taken = [], [], set(), {}
    for e in evals:
        skipped += e["skipped"]
        if not e["refs"]:
            skipped.append(f"{e['dir'].name}: no reference audio")
            continue
        if e["title"] is None:
            dup = all(g["sha"] in titled_shas for g in e["refs"])
            skipped.append(f"{e['dir'].name}: " + ("duplicate of a titled evaluation" if dup else "no '# Song — Artist' title"))
            continue
        artist, song = e["title"]
        slug = tones.slug(artist, song)
        for g in e["refs"]:
            if g["sha"] in seen:
                skipped.append(f"{e['dir'].name}/{g['file'].name}: duplicate audio")
                continue
            seen.add(g["sha"])
            role, n = g["role"], 1
            while (slug, role) in taken:
                n += 1
                role = f"{g['role']}-{n}"
            taken[(slug, role)] = g["sha"]
            separated = "demucs" in g["role"]
            jobs.append({
                "artist": artist, "song": song, "role": role,
                "kind": "separated" if separated else "stem",
                "separator": "demucs htdemucs_6s" if separated else None,
                "reference": g["file"], "track": e["track"], "origin": str(e["dir"]),
            })
    return jobs, skipped


def _analyze(job: dict) -> tuple[dict, str]:
    out = tempfile.mkdtemp(prefix="tone-import-")
    tones.analyze_audio(job["reference"], Path(out), job["track"])
    return job, out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="+")
    p.add_argument("--root", default=str(tones.repo_root()))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--jobs", type=int, default=4)
    a = p.parse_args(argv)

    jobs, skipped = plan([Path(s) for s in a.sources])
    for j in jobs:
        print(f"import  {j['artist']} — {j['song']} [{j['role']}, {j['kind']}{', +track' if j['track'] else ''}]  <- {j['reference']}")
    for s in skipped:
        print(f"skip    {s}")
    if a.dry_run:
        return 0

    import shutil

    failed = 0
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        futures = [pool.submit(_analyze, j) for j in jobs]
        for fut in futures:
            try:
                job, out = fut.result()
            except BaseException as exc:  # analyze raises SystemExit on bad audio
                failed += 1
                print(f"FAILED  {exc}", file=sys.stderr, flush=True)
                continue
            tones.add(Path(a.root), job["artist"], job["song"], job["role"], Path(out), job["kind"],
                      reference=job["reference"], track=job["track"], separator=job["separator"], replace=True)
            shutil.rmtree(out, ignore_errors=True)
            print(f"done    {tones.slug(job['artist'], job['song'])}/{job['role']}", flush=True)
    print(f"{len(jobs) - failed} imported, {failed} failed, {len(skipped)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
