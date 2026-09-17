"""Tone library: stored analyses of a song's guitar, looked up before analyzing.

An entry is `<root>/<slug>/tone.json` plus one directory per role (lead,
rhythm, …) holding the analyzed audio (`reference.<ext>`) and the output of
`analyze` (plus `harmonics` when the full track, `track.<ext>`, is stored), so
any entry can be re-analyzed when the analyzer changes. Roots, in lookup order:
`TONE_ANALYZER_TONES_PATH` (`:`-separated), `~/.tone-analyzer/tones`, and the
`tones/` shipped with the plugin.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any

from tone_analyzer import _common

SCHEMA_VERSION = 1
META = "tone.json"
KINDS = ("stem", "separated", "track")
FUZZY_MIN = 0.8


class LibraryError(Exception):
    """A library operation that must not proceed (exit 2 on the CLI)."""


# --------------------------------------------------------------------------- naming


def _ascii_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", text.replace("'", ""))


def _drop_leading_the(words: list[str]) -> list[str]:
    return words[1:] if len(words) > 1 and words[0] == "the" else words


def slug(artist: str, song: str) -> str:
    return "-".join(_drop_leading_the(_ascii_words(artist)) + _drop_leading_the(_ascii_words(song)))


def _norm(text: str) -> str:
    return " ".join(_drop_leading_the(_ascii_words(text)))


# --------------------------------------------------------------------------- roots


def repo_root() -> Path:
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    base = Path(plugin) if plugin else Path(__file__).resolve().parent.parent
    return base / "tones"


def home_root() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))) / ".tone-analyzer" / "tones"


def default_roots() -> list[Path]:
    extra = [Path(p).expanduser() for p in os.environ.get("TONE_ANALYZER_TONES_PATH", "").split(":") if p]
    return extra + [home_root(), repo_root()]


# --------------------------------------------------------------------------- read


def _entries(roots: list[Path]) -> list[dict[str, Any]]:
    out = []
    for root in roots:
        if not root.is_dir():
            continue
        for meta_path in sorted(root.glob(f"*/{META}")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            out.append(
                {
                    "slug": meta["slug"],
                    "artist": meta["artist"],
                    "song": meta["song"],
                    "aliases": meta.get("aliases", []),
                    "roles": sorted(meta["roles"]),
                    "kinds": {r: v["reference"]["kind"] for r, v in sorted(meta["roles"].items())},
                    "root": str(root),
                    "path": str(meta_path.parent),
                }
            )
    return out


def list_entries(roots: list[Path] | None = None) -> list[dict[str, Any]]:
    return _entries(default_roots() if roots is None else roots)


def _score(query: str, entry: dict[str, Any]) -> float:
    q = _norm(query)
    artist, song = _norm(entry["artist"]), _norm(entry["song"])
    names = [f"{artist} {song}", f"{song} {artist}", song] + [_norm(a) for a in entry["aliases"]]
    if q in names:
        return 1.0
    return max(difflib.SequenceMatcher(None, q, n).ratio() for n in names)


def find(query: str, roots: list[Path] | None = None) -> list[dict[str, Any]]:
    scored = [(s, e) for e in list_entries(roots) if (s := _score(query, e)) >= FUZZY_MIN]
    scored.sort(key=lambda se: -se[0])  # stable: root order kept on ties
    return [{**e, "score": round(s, 3)} for s, e in scored]


# --------------------------------------------------------------------------- write


def _audio_facts(path: Path) -> dict[str, Any]:
    facts: dict[str, Any] = {"sha256": _common.sha256_file(path), "duration_s": None, "sample_rate_hz": None}
    try:
        import soundfile as sf

        info = sf.info(str(path))
        facts["duration_s"] = round(info.frames / info.samplerate, 4)
        facts["sample_rate_hz"] = int(info.samplerate)
    except Exception:
        pass
    return facts


def _analyzer_version() -> str:
    try:
        from importlib.metadata import version

        return version("tone-analyzer")
    except Exception:
        from tone_analyzer import __version__

        return __version__


def _strip_source_path(json_path: Path) -> None:
    if not json_path.is_file():
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    src = data.get("source")
    if isinstance(src, dict) and src.get("path"):
        src["path"] = Path(src["path"]).name
        json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


REFERENCE_STEM = "reference"
TRACK_STEM = "track"


def _stored(directory: Path, stem: str) -> Path | None:
    hits = sorted(q for q in directory.glob(f"{stem}.*") if q.is_file()) if directory.is_dir() else []
    return hits[0] if hits else None


def _store_audio(src: Path, directory: Path, stem: str) -> Path:
    """Copy src to directory/<stem><suffix>, replacing any previously stored one."""
    src = Path(src).expanduser().resolve()
    dst = directory / f"{stem}{src.suffix.lower()}"
    if dst.exists() and dst.resolve() == src:
        return dst
    for old in directory.glob(f"{stem}.*"):
        old.unlink()
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def add(
    root: Path,
    artist: str,
    song: str,
    role: str,
    analysis_dir: Path,
    reference_kind: str,
    reference: Path | None = None,
    track: Path | None = None,
    separator: str | None = None,
    aliases: list[str] | None = None,
    replace: bool = False,
) -> Path:
    root, analysis_dir = Path(root).expanduser(), Path(analysis_dir)
    if reference_kind not in KINDS:
        raise LibraryError(f"reference kind must be one of {', '.join(KINDS)}, got '{reference_kind}'")
    fp_path = analysis_dir / "fingerprint.json"
    if not fp_path.is_file():
        raise LibraryError(f"no fingerprint.json in {analysis_dir} — run analyze first")
    role = "-".join(_ascii_words(role))
    if not role:
        raise LibraryError("role must not be empty")

    entry = root / slug(artist, song)
    meta_path = entry / META
    meta = (
        json.loads(meta_path.read_text(encoding="utf-8"))
        if meta_path.is_file()
        else {"schema_version": SCHEMA_VERSION, "slug": entry.name, "artist": artist, "song": song,
              "aliases": [], "roles": {}}
    )
    if role in meta["roles"] and not replace:
        raise LibraryError(f"{entry.name}/{role} already exists — pass --replace to overwrite")
    meta["aliases"] = sorted(set(meta.get("aliases", [])) | set(aliases or []))
    fingerprint = json.loads(fp_path.read_text(encoding="utf-8"))

    # analysis files: replace everything in the role dir except the stored reference audio
    dest = entry / role
    dest.mkdir(parents=True, exist_ok=True)
    if analysis_dir.resolve() != dest.resolve():
        for old in dest.iterdir():
            if old.name.startswith(f"{REFERENCE_STEM}."):
                continue
            shutil.rmtree(old) if old.is_dir() else old.unlink()
        for item in analysis_dir.iterdir():
            target = dest / item.name
            shutil.copytree(item, target) if item.is_dir() else shutil.copy2(item, target)
    for name in ("fingerprint.json", "harmonics.json"):
        _strip_source_path(dest / name)

    ref_file = _store_audio(reference, dest, REFERENCE_STEM) if reference is not None else _stored(dest, REFERENCE_STEM)
    if ref_file is not None:
        ref_facts = {"file": ref_file.relative_to(entry).as_posix(), **_audio_facts(ref_file)}
    else:
        src = fingerprint.get("source", {})
        ref_facts = {"file": None, **{k: src.get(k) for k in ("sha256", "duration_s", "sample_rate_hz")}}

    track_file = _store_audio(track, entry, TRACK_STEM) if track is not None else None
    old_track = meta["roles"].get(role, {}).get("track")
    if track_file is not None:
        track_facts = {"file": track_file.name, **_audio_facts(track_file)}
    else:
        track_facts = old_track if old_track and _stored(entry, TRACK_STEM) else None

    meta["roles"][role] = {
        "reference": {"kind": reference_kind, "separator": separator, **ref_facts},
        "track": track_facts,
        "analyzer_version": _analyzer_version(),
        "fingerprint_schema": fingerprint.get("schema_version"),
        "created": _dt.date.today().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def analyze_audio(reference: Path, out_dir: Path, track: Path | None = None) -> Path:
    """analyze the reference; with a track, read the harmonics of its notes on the track."""
    import contextlib
    import io

    from tone_analyzer import analyze, harmonics

    with contextlib.redirect_stdout(io.StringIO()):
        if analyze.main([str(reference), "--out-dir", str(out_dir)]) != 0:
            raise LibraryError(f"analyze failed on {reference}")
        if track is not None:
            fp = json.loads((out_dir / "fingerprint.json").read_text(encoding="utf-8"))
            args = [str(track), "--out-dir", str(out_dir)]
            for n in fp.get("notes", []):
                args += ["--at", str(n["start_s"]), "--midi", str(n["midi"])]
            if len(args) > 3 and harmonics.main(args) != 0:
                raise LibraryError(f"harmonics failed on {track}")
    return out_dir


def reanalyze(entry: Path, roles: list[str] | None = None) -> list[str]:
    """Re-run the analysis of every role that has its reference audio stored. Returns the roles done."""
    import tempfile

    entry = Path(entry)
    meta = json.loads((entry / META).read_text(encoding="utf-8"))
    done = []
    for role, info in sorted(meta["roles"].items()):
        if roles and role not in roles:
            continue
        ref = _stored(entry / role, REFERENCE_STEM)
        if ref is None:
            continue
        track = _stored(entry, TRACK_STEM) if info.get("track") else None
        with tempfile.TemporaryDirectory(prefix="tone-analyzer-reanalyze-") as tmp:
            analyze_audio(ref, Path(tmp), track)
            add(entry.parent, meta["artist"], meta["song"], role, Path(tmp), info["reference"]["kind"],
                track=None, separator=info["reference"].get("separator"), replace=True)
        done.append(role)
    return done


# --------------------------------------------------------------------------- CLI


def _print_entries(entries: list[dict[str, Any]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return
    for e in entries:
        roles = ", ".join(f"{r} ({k})" for r, k in e["kinds"].items())
        print(f"{e['artist']} — {e['song']}  [{roles}]  {e['path']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tone-analyzer tones", description="Library of stored song analyses.")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("find", help="search the library roots")
    f.add_argument("query", nargs="+")
    f.add_argument("--json", action="store_true")

    ls = sub.add_parser("list", help="every entry in every root")
    ls.add_argument("--json", action="store_true")

    a = sub.add_parser("add", help="store an analysis directory as a song role")
    a.add_argument("--artist", required=True)
    a.add_argument("--song", required=True)
    a.add_argument("--role", required=True, help="lead, rhythm, guitars, acoustic, …")
    a.add_argument("--analysis", required=True, help="an analyze --out-dir (optionally with harmonics.json)")
    a.add_argument("--reference-kind", required=True, choices=KINDS)
    a.add_argument("--reference", default=None, help="the analyzed audio; stored as <role>/reference.<ext>")
    a.add_argument("--track", default=None, help="the full track harmonics were read on; stored as track.<ext>")
    a.add_argument("--separator", default=None, help="e.g. 'demucs 4.1.0 htdemucs_6s'")
    a.add_argument("--alias", action="append", default=[])
    a.add_argument("--root", default=None, help="library root (default ~/.tone-analyzer/tones)")
    a.add_argument("--replace", action="store_true")

    r = sub.add_parser("reanalyze", help="re-run the analysis from the stored audio")
    r.add_argument("query", nargs="*", help="song to reanalyze (omit with --all)")
    r.add_argument("--all", action="store_true")
    r.add_argument("--role", action="append", default=[])

    args = p.parse_args(argv)
    if args.cmd == "reanalyze":
        if args.all == bool(args.query):
            print("tones reanalyze: pass a song or --all", file=sys.stderr)
            return 2
        targets = list_entries() if args.all else find(" ".join(args.query))[:1]
        if not targets:
            print("tones reanalyze: no match", file=sys.stderr)
            return 1
        try:
            for e in targets:
                done = reanalyze(Path(e["path"]), args.role or None)
                print(f"{e['path']}: {', '.join(done) or 'no stored audio'}")
        except LibraryError as exc:
            print(f"tones: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "find":
        hits = find(" ".join(args.query))
        _print_entries(hits, args.json)
        return 0 if hits else 1
    if args.cmd == "list":
        _print_entries(list_entries(), args.json)
        return 0
    try:
        entry = add(
            Path(args.root) if args.root else home_root(), args.artist, args.song, args.role,
            Path(args.analysis), args.reference_kind,
            reference=Path(args.reference) if args.reference else None,
            track=Path(args.track) if args.track else None,
            separator=args.separator, aliases=args.alias, replace=args.replace,
        )
    except LibraryError as exc:
        print(f"tones: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"tones: {exc}", file=sys.stderr)
        return 1
    print(str(entry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
