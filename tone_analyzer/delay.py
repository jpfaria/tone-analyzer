#!/usr/bin/env python3
"""Delay lags of ONE audio, ranked by how many independent windows vote for them.

An echo is a scaled copy of the signal at a fixed lag D: it leaves a ripple of period 1/D in
log|X(f)|^2, a narrow peak at quefrency D in the cepstrum. Re-played notes are not copies, so a
player's rhythm does not show up. The HEIGHT of that peak is not a criterion: a wobbling tape
delay inside a full mix drops from ~700x to ~8x the background (no delay: 2-4x). What separates a
delay from chance is PERSISTENCE — the same lag among the top peaks of most windows — together
with SPREAD: a copy lands on the same sample in every window (spread 0.00-0.05 ms), while a
rhythmic grid also persists (unrelated attacks at the same spacing) but wanders by 0.5-2 ms.
Known limit: a wobbling tape delay has the spread of a rhythm; one audio cannot tell them apart.

Measures only. Whether the audio "has a delay" is the orchestrator's decision (tone-builder).
Validated 17-18/09/2026 on known truth: error < 1 ms; survives a 4 % mix, reverb on top, the
guitar 5 dB under a real backing, AAC 128k and a demucs stem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

from tone_analyzer import _common
from tone_analyzer.analyze import resolve_out_dir

SCHEMA_VERSION = 1
FILENAME = "delay.json"
WINDOW_S, HOP_S = 20.0, 10.0
LO_MS, HI_MS = 150.0, 1500.0
BAND_HZ = (150.0, 6000.0)              # where a guitar lives
POOL_MS = (0.0, 0.5)                  # an echo is SHARP (a copy); two unrelated attacks at the same spacing smear over ms — wide pooling turns rhythm into "delay"
TOP_PER_WINDOW, TOLERANCE_MS, SILENCE_RMS = 5, 4.0, 1e-4


def window_peaks(x: np.ndarray, sr: int, top: int = TOP_PER_WINDOW) -> list[tuple[float, float]]:
    """[(lag_ms, energy over the local cepstral background)], strongest first."""
    n = 1 << int(np.ceil(np.log2(len(x))))
    spec = np.fft.rfft(x * np.hanning(len(x)), n)
    f = np.fft.rfftfreq(n, 1 / sr)
    log_power = np.log(np.abs(spec) ** 2 + 1e-12)
    band = (f >= BAND_HZ[0]) & (f <= BAND_HZ[1])
    log_power = np.where(band, log_power - np.mean(log_power[band]), 0.0)
    cep = np.fft.irfft(log_power, n)
    pad, lo, hi = int(0.08 * sr), int(LO_MS / 1000 * sr), int(HI_MS / 1000 * sr)
    hi = min(hi, len(cep) // 2 - pad - 1)
    seg = cep[lo - pad: hi + pad]
    best: list[tuple[float, float]] = []
    best_score = -1.0
    for pool_ms in POOL_MS:
        e = uniform_filter1d(seg ** 2, max(1, int(pool_ms / 1000 * sr)))
        r = (e / (uniform_filter1d(e, int(0.05 * sr)) + 1e-18))[pad:-pad]   # local background (mean: 100x faster than a median)
        r = r / (np.median(r) + 1e-18)
        peaks = []
        for _ in range(top):
            i = int(np.argmax(r))
            peaks.append(((lo + i) / sr * 1000.0, float(r[i])))
            r[max(0, i - int(0.015 * sr)): i + int(0.015 * sr)] = 0.0
        score = peaks[0][1] / max(peaks[1][1], 1e-9)
        if score > best_score:
            best, best_score = peaks, score
    return best


def measure(signal: np.ndarray, sr: int, window_s: float = WINDOW_S, hop_s: float = HOP_S) -> dict:
    x = _common.mono_mixdown(np.asarray(signal, dtype=np.float64)) if np.ndim(signal) > 1 else np.asarray(signal, dtype=np.float64)
    w, h = int(window_s * sr), int(hop_s * sr)
    votes: list[tuple[float, float]] = []
    windows = 0
    for k in range(0, max(1, len(x) - w + 1), h):
        seg = x[k:k + w]
        if len(seg) < w // 2 or np.sqrt(np.mean(seg ** 2)) < SILENCE_RMS:
            continue
        windows += 1
        votes += window_peaks(seg, sr)
    votes.sort()
    groups: list[list[tuple[float, float]]] = []
    for v in votes:
        if groups and v[0] - groups[-1][-1][0] <= TOLERANCE_MS:
            groups[-1].append(v)
        else:
            groups.append([v])
    cands = [{"time_ms": float(np.median([g[0] for g in grp])), "windows": len(grp),
              "share": len(grp) / max(windows, 1),
              "spread_ms": float(np.std([g[0] for g in grp])), "median_strength": float(np.median([g[1] for g in grp]))}
             for grp in groups]
    cands.sort(key=lambda c: (-c["windows"], -c["median_strength"]))
    return {"window_s": window_s, "hop_s": hop_s, "windows": windows, "candidates": cands[:8]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Delay lags ranked by persistence across windows. Measures only.")
    p.add_argument("input")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    path = Path(a.input).expanduser().resolve()
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    signal, sr = _common.load_audio(path)
    out = {"schema_version": SCHEMA_VERSION,
           "source": {"path": path.name, "sha256": _common.sha256_file(path), "sample_rate_hz": int(sr)},
           **measure(signal, sr)}
    out_dir = resolve_out_dir(a.out_dir)
    (out_dir / FILENAME).write_text(json.dumps(_common.round_for_json(out, ndigits=4), indent=2, sort_keys=True), encoding="utf-8")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
