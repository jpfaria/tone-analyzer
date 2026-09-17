#!/usr/bin/env python3
"""Separate the guitar from a full track with the demucs CLI.

Pure function over files: in = one track, out = `guitar.wav`, `no_guitar.wav`
and `separate.json` in --out-dir, always 48 kHz float (a 44.1 kHz stem read as
48 kHz shifts every note +1.5 semitone). demucs is not reinvented and not
installed here: missing → exit 3 with the install hint. demucs downloads its
model on first use; this is the only command that may reach the network.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from tone_analyzer import _common
from tone_analyzer.analyze import resolve_out_dir

TARGET_SR = 48000
DEFAULT_MODEL = "htdemucs_6s"
INSTALL_HINT = "demucs not found — install it: pipx install demucs"
STEMS = ("guitar", "no_guitar")


def _to_48k(src: Path, dst: Path) -> None:
    x, sr = sf.read(str(src), dtype="float32", always_2d=True)
    if sr != TARGET_SR:
        g = math.gcd(TARGET_SR, sr)
        x = resample_poly(x, TARGET_SR // g, sr // g, axis=0).astype(np.float32)
    sf.write(str(dst), x, TARGET_SR, subtype="FLOAT")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Separate guitar / no_guitar from a full track with demucs (48 kHz out).")
    p.add_argument("input")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    a = p.parse_args(argv)

    demucs = shutil.which("demucs")
    if demucs is None:
        print(INSTALL_HINT, file=sys.stderr)
        return 3
    track = Path(a.input).expanduser().resolve()
    if not track.is_file():
        print(f"file not found: {track}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="tone-analyzer-demucs-") as tmp:
        proc = subprocess.run(
            [demucs, "--two-stems", "guitar", "-n", a.model, "-o", tmp, str(track)],
            capture_output=True, text=True,
        )
        stem_dir = Path(tmp) / a.model / track.stem
        if proc.returncode != 0 or not all((stem_dir / f"{s}.wav").is_file() for s in STEMS):
            tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-20:])
            print(f"demucs failed (exit {proc.returncode}):\n{tail}", file=sys.stderr)
            return 1
        out_dir = resolve_out_dir(a.out_dir)
        for s in STEMS:
            _to_48k(stem_dir / f"{s}.wav", out_dir / f"{s}.wav")

    meta = {
        "separator": f"demucs {a.model}",
        "sample_rate_hz": TARGET_SR,
        "source": {"path": track.name, "sha256": _common.sha256_file(track)},
        "stems": [f"{s}.wav" for s in STEMS],
    }
    (out_dir / "separate.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
