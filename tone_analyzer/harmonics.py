#!/usr/bin/env python3
"""Harmonic levels of ONE audio at given or detected notes.

Pure function: in = one audio path, out = harmonics.json in --out-dir.
`--at SEC --midi M` pairs measure at a given attack time and note — this is how
an orchestrator reads a full mix at notes located elsewhere. `--auto` detects
the notes in this same audio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tone_analyzer import _common, notes
from tone_analyzer.analyze import resolve_out_dir

SCHEMA_VERSION = 1
FILENAME = "harmonics.json"


def build(signal, sr: int, audio_path: Path, targets: list[tuple[float, int]]) -> dict:
    mono = _common.mono_mixdown(signal)
    rows = []
    for start_s, midi in targets:
        f0 = 440.0 * 2.0 ** ((midi - 69) / 12.0)
        h = notes.harmonic_levels(mono, sr, start_s, f0)
        if h is None:
            continue
        rows.append({"start_s": start_s, "midi": midi, "name": notes.midi_name(midi), "f0_hz": f0, **h})
    return _common.round_for_json(
        {
            "schema_version": SCHEMA_VERSION,
            "source": {"path": str(audio_path), "sample_rate_hz": int(sr)},
            "notes": rows,
        },
        ndigits=4,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Harmonic levels of one audio at given or detected notes.")
    p.add_argument("input")
    p.add_argument("--at", type=float, action="append", default=[], help="attack time in seconds")
    p.add_argument("--midi", type=int, action="append", default=[], help="MIDI note for the matching --at")
    p.add_argument("--auto", action="store_true", help="detect the notes in this audio")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    if len(a.at) != len(a.midi) or (not a.auto and not a.at):
        print("harmonics: pass --auto, or --at and --midi in pairs", file=sys.stderr)
        return 2
    audio_path = Path(a.input).expanduser().resolve()
    signal, sr = _common.load_audio(audio_path)
    targets = list(zip(a.at, a.midi))
    if a.auto:
        targets += [(n["start_s"], n["midi"]) for n in notes.detect_notes(_common.mono_mixdown(signal), sr)]
    out_dir = resolve_out_dir(a.out_dir)
    payload = build(signal, sr, audio_path, targets)
    (out_dir / FILENAME).write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
