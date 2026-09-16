"""Synthetic guitar-like notes with known harmonic amplitudes, for tests only.

Recorded music cannot ship in this public repo, so every audio fixture that
needs a known truth is synthesized here.
"""

from __future__ import annotations

import numpy as np


def midi_to_hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def harmonic_note(
    midi: int,
    sr: int,
    dur_s: float,
    harm_db: list[float],
    attack_s: float = 0.005,
    decay_s: float = 1.5,
) -> np.ndarray:
    """Sum of harmonics k=1..len(harm_db) at the given dB (H1 first), plucked envelope."""
    n = int(round(dur_s * sr))
    t = np.arange(n) / sr
    f0 = midi_to_hz(midi)
    x = np.zeros(n)
    for k, db in enumerate(harm_db, start=1):
        if k * f0 >= sr / 2:
            break
        x += 10.0 ** (db / 20.0) * np.sin(2 * np.pi * k * f0 * t)
    env = np.minimum(t / attack_s, 1.0) * np.exp(-t / decay_s)
    x *= env
    peak = np.abs(x).max()
    if peak > 0:
        x *= 0.5 / peak
    return x.astype(np.float32)


def note_sequence(
    midis: list[int],
    sr: int,
    note_s: float,
    gap_s: float,
    harm_db: list[float],
) -> tuple[np.ndarray, list[float]]:
    """Notes separated by silence. Starts after one leading gap."""
    parts = [np.zeros(int(round(gap_s * sr)), dtype=np.float32)]
    starts = []
    t = gap_s
    for m in midis:
        starts.append(round(t, 6))
        parts.append(harmonic_note(m, sr, note_s, harm_db))
        parts.append(np.zeros(int(round(gap_s * sr)), dtype=np.float32))
        t += note_s + gap_s
    return np.concatenate(parts), starts
