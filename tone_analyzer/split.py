#!/usr/bin/env python3
"""Split a separated stereo guitar into its panned parts and label each rhythm or lead.

demucs hands back ONE guitar. When two takes are panned apart (left and right
barely correlate) each side is its own part; when the guitar sits in the center
there is nothing to split and the verdict says so. Each part is labeled from
what it plays: rhythm = sounds almost all the time with 2+ notes at once; lead =
comes and goes, one note at a time. Anything else is `undetermined` — never a
guess. Measured on Creed / Green Day (docs/split-guitars/README.md).

Pure function over files: in = one guitar WAV, out = one mono WAV per part and
`split.json` (verdict, reason, per-part numbers) in --out-dir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from tone_analyzer.analyze import resolve_out_dir

# Above this left/right sample correlation both sides carry the same take: centered.
SPLIT_MAX_CORR = 0.5
# A frame is "playing" within this many dB of the part's loudest frame.
ACTIVE_DB = 30.0
# rhythm plays at least this fraction of the song; lead plays less.
BUSY_FRACTION = 0.75
# Mean pitch classes above 0.6 of the frame's strongest: rhythm ≥, lead <.
CHORD_NOTES = 2.0
_SR = 22050
_HOP = 2048


def verdict(x: np.ndarray, sr: int) -> dict[str, Any]:
    """Whether the guitar can be split by side, and why."""
    if x.ndim == 1 or x.shape[1] == 1:
        return {"split": False, "reason": "mono: no left/right to split", "lr_correlation": None}
    corr = float(np.corrcoef(x[:, 0], x[:, 1])[0, 1])
    if corr >= SPLIT_MAX_CORR:
        return {
            "split": False,
            "reason": f"guitar in the center: left and right are the same take (correlation {corr:.2f})",
            "lr_correlation": corr,
        }
    return {
        "split": True,
        "reason": f"two takes panned apart: left and right differ (correlation {corr:.2f})",
        "lr_correlation": corr,
    }


def _features(y: np.ndarray, sr: int) -> dict[str, float]:
    y = y.astype(np.float32)
    if sr != _SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=_SR)
    db = 20 * np.log10(librosa.feature.rms(y=y, hop_length=_HOP)[0] + 1e-9)
    active = db > db.max() - ACTIVE_DB
    chroma = librosa.feature.chroma_cqt(y=y, sr=_SR, hop_length=_HOP)
    n = min(len(active), chroma.shape[1])
    active, chroma = active[:n], chroma[:, :n]
    strong = (chroma / (chroma.max(axis=0) + 1e-9) > 0.6).sum(axis=0)
    return {
        "active_fraction": float(active.mean()),
        "notes_at_once": float(strong[active].mean()) if active.any() else 0.0,
    }


def _role(f: dict[str, float]) -> str:
    busy = f["active_fraction"] >= BUSY_FRACTION
    chords = f["notes_at_once"] >= CHORD_NOTES
    if busy and chords:
        return "rhythm"
    if not busy and not chords:
        return "lead"
    return "undetermined"


def _part(y: np.ndarray, sr: int, side: str) -> dict[str, Any]:
    f = _features(y, sr)
    role = _role(f)
    return {
        "name": role if side == "C" else f"{role}-{side}",
        "side": side,
        "role": role,
        **f,
        "signal": y,
    }


def split_guitar(x: np.ndarray, sr: int) -> list[dict[str, Any]]:
    """One part per side when the takes are panned apart, else one centered part."""
    if verdict(x, sr)["split"]:
        return [_part(x[:, 0], sr, "L"), _part(x[:, 1], sr, "R")]
    mono = x if x.ndim == 1 else x.mean(axis=1)
    return [_part(mono, sr, "C")]


def write_parts(src: Path, out_dir: Path) -> dict[str, Any]:
    """Write one WAV per part and `split.json` into out_dir; return the json."""
    x, sr = sf.read(str(src), dtype="float32")
    v = verdict(x, sr)
    meta_parts = []
    for part in split_guitar(x, sr):
        file = f"{part['name']}.wav"
        sf.write(str(out_dir / file), part.pop("signal"), sr, subtype="FLOAT")
        meta_parts.append({"file": file, **part})
    meta = {**v, "source": src.name, "parts": meta_parts}
    (out_dir / "split.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{'split' if v['split'] else 'not split'}: {v['reason']}", file=sys.stderr)
    for part in meta_parts:
        print(f"  {part['file']}: {part['role']} (plays {part['active_fraction']:.0%}, "
              f"{part['notes_at_once']:.1f} notes at once)", file=sys.stderr)
    return meta


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Split a separated guitar into its panned parts, labeled rhythm/lead.")
    p.add_argument("input")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    src = Path(a.input).expanduser().resolve()
    if not src.is_file():
        print(f"file not found: {src}", file=sys.stderr)
        return 2
    out_dir = resolve_out_dir(a.out_dir)
    write_parts(src, out_dir)
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
