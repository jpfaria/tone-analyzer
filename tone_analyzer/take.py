#!/usr/bin/env python3
"""Metrics of ONE recorded take (typically one library note).

Measures only. Whether a take is good enough is the orchestrator's decision
(tone-builder), not this module's.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from tone_analyzer import _common, notes

SATURATION = 0.999
FILENAME = "take.json"


def saturated_samples(signal: np.ndarray, threshold: float = SATURATION) -> int:
    """Samples at or near full scale, counted on EVERY channel (no mixdown).

    A mono mixdown of a stereo file that clips on one side only halves that
    peak and hides the clipping.
    """
    return int(np.sum(np.abs(np.asarray(signal)) > threshold))


def _rms_db(x: np.ndarray) -> float:
    return float(20.0 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12))


def take_onset(mono: np.ndarray, sr: int, rel: float = 0.1, block_s: float = 0.005) -> int | None:
    """First 5 ms block whose peak passes 10 % of the take's peak.

    A take is one note cut close to its attack (library notes keep ~20 ms of
    pre-roll), so the envelope-rise detector used for full tracks does not fit:
    its block is longer than the pre-roll and it never sees the rise.
    """
    x = np.abs(np.asarray(mono, dtype=np.float64))
    if len(x) == 0 or x.max() <= 1e-6:
        return None
    block = max(1, int(round(block_s * sr)))
    lim = rel * x.max()
    for i in range(0, len(x), block):
        if x[i:i + block].max() > lim:
            return i
    return None


def take_metrics(signal: np.ndarray, sr: int, dur_s: float = 0.6) -> dict:
    mono = np.asarray(_common.mono_mixdown(signal), dtype=np.float64)
    duration_s = len(mono) / sr
    peak = float(np.max(np.abs(signal))) if len(mono) else 0.0
    found = take_onset(mono, sr)
    onset = found if found is not None else 0
    out = {
        "duration_s": duration_s,
        "onset_s": onset / sr,
        "midi": None,
        "name": None,
        "f0_hz": None,
        "pitch_confidence": None,
        "saturated_samples": saturated_samples(signal),
        "peak_db": float(20.0 * np.log10(peak + 1e-12)),
        "noise_floor_db": None,
        "signal_db": None,
        "snr_db": None,
    }
    if found is None:
        return out
    frame = int(round(notes.FRAME_S * sr))
    seg = mono[onset:onset + int(round(dur_s * sr))]
    out["signal_db"] = _rms_db(seg)
    if len(seg) >= frame:
        f0, conf = notes.pitch_autocorr(seg[len(seg) // 2 - frame // 2:len(seg) // 2 - frame // 2 + frame], sr)
        if conf > 0.8:
            midi = int(round(notes.hz_to_midi(f0)))
            out.update({"midi": midi, "name": notes.midi_name(midi), "f0_hz": f0, "pitch_confidence": conf})
    pre = mono[:onset]
    if len(pre) >= int(0.010 * sr):
        out["noise_floor_db"] = _rms_db(pre)
        out["snr_db"] = out["signal_db"] - out["noise_floor_db"]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Metrics of one recorded take.")
    p.add_argument("input")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    from tone_analyzer.analyze import resolve_out_dir

    audio_path = Path(a.input).expanduser().resolve()
    signal, sr = _common.load_audio(audio_path)
    out_dir = resolve_out_dir(a.out_dir)
    payload = _common.round_for_json({"source": {"path": str(audio_path), "sample_rate_hz": int(sr)},
                                      **take_metrics(signal, sr)}, ndigits=4)
    (out_dir / FILENAME).write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
