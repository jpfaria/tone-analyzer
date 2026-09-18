"""Which notes sound at one attack of ONE guitar audio, and levels at given frequencies.

Pure functions, no I/O. The level reading is the one validated for single notes
(Hann window over 0.6 s from the attack, peak within +-1.2 %, neighbourhood median
at 0.90-0.96 and 1.04-1.10 of the frequency), taken at any list of frequencies so a
chord can be read at the harmonics of each of its notes.
"""

from __future__ import annotations

import numpy as np

from tone_analyzer.notes import midi_name, note_onsets

PEAK_TOL = 0.012
NEIGH_LO = (0.90, 0.96)
NEIGH_HI = (1.04, 1.10)


def levels_at(signal: np.ndarray, sr: int, start_s: float, freqs_hz: list[float],
              dur_s: float = 0.6) -> dict | None:
    x = np.asarray(signal, dtype=np.float64)
    ini = int(round(start_s * sr))
    n = min(int(round(dur_s * sr)), len(x) - ini)
    if n < int(0.3 * sr):
        return None
    seg = x[ini:ini + n] * np.hanning(n)
    power = np.abs(np.fft.rfft(seg, 4 * n)) ** 2
    freqs = np.fft.rfftfreq(4 * n, 1 / sr)
    level: list[float | None] = []
    neigh: list[float | None] = []
    prom: list[float | None] = []
    for f in freqs_hz:
        peak = (freqs > f * (1 - PEAK_TOL)) & (freqs < f * (1 + PEAK_TOL))
        around = (((freqs > f * NEIGH_LO[0]) & (freqs < f * NEIGH_LO[1]))
                  | ((freqs > f * NEIGH_HI[0]) & (freqs < f * NEIGH_HI[1])))
        if f > 0.9 * sr / 2 or not peak.any() or not around.any():
            level.append(None)
            neigh.append(None)
            prom.append(None)
            continue
        lv = 10.0 * np.log10(power[peak].max() + 1e-30)
        nb = 10.0 * np.log10(np.median(power[around]) + 1e-30)
        level.append(float(lv))
        neigh.append(float(nb))
        prom.append(float(lv - nb))
    return {"level_db": level, "neighbour_db": neigh, "prominence_db": prom}


DETECTORS = ("salience", "basic-pitch")
SAL_PROM_DB = 13.0        # the method's prominence gate
SAL_HARM = 8              # harmonics that vote for a candidate
EXPLAIN_HARM = 16         # harmonics a chosen note takes away from the others
MIN_FREE = 3              # a candidate needs this many prominent, unexplained harmonics
MAX_NOTES = 6             # six strings
COLLIDE = 0.024           # two frequencies closer than this are the same peak
MIDI_RANGE = range(40, 89)   # E2..E6


def _hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def salience_set(signal: np.ndarray, sr: int, start_s: float, dur_s: float = 0.6) -> list[int]:
    """Greedy: the candidate with the most prominence on unexplained harmonics wins, its
    harmonics become explained, repeat.

    An exact octave doubling (+12/+24/+36 semitones) of an already-chosen note is a note
    whose ENTIRE spectrum is a subset of the chosen note's (k * f0_upper = 2k * f0_lower for
    every k), so once one side of the pair is explained there is nothing left to distinguish
    the other from silence -- this method has no way to tell "only the lower note" from
    "both the lower note and its octave" apart from magnitude spectrum alone. In practice this
    means: when a bigger chord's OTHER notes also collide with a doubled note's odd harmonics
    (measured, not assumed -- see tests/task-2 report), only one member of the pair survives
    MIN_FREE and gets reported; which one survives is whichever the greedy order explains
    first, not necessarily the lower note. The DI choice (tone-builder) decides whether the
    doubling is actually there. This reduction is NOT guaranteed to trigger for every doubled
    pair in isolation (see task-2 report: a 2-note octave-only input can still report both
    notes, plus spurious neighbours, when no other note's collisions help empty out the
    doubled note's free harmonics) -- it is an emergent side effect of MIN_FREE against
    whatever else is in the mix, not a dedicated octave filter.
    """
    peaks: dict[int, list[tuple[float, float]]] = {}
    for m in MIDI_RANGE:
        f0 = _hz(m)
        h = levels_at(signal, sr, start_s, [f0 * k for k in range(1, SAL_HARM + 1)], dur_s)
        if h is None:
            return []
        peaks[m] = [(f0 * k, p) for k, p in enumerate(h["prominence_db"], 1)
                    if p is not None and p >= SAL_PROM_DB]
    explained: list[float] = []
    chosen: list[int] = []
    while len(chosen) < MAX_NOTES:
        best, best_s = None, 0.0
        for m, pk in peaks.items():
            if m in chosen:
                continue
            free = [p for f, p in pk if not any(abs(f - e) / e < COLLIDE for e in explained)]
            if len(free) >= MIN_FREE and sum(free) > best_s:
                best, best_s = m, sum(free)
        if best is None:
            break
        chosen.append(best)
        explained += [_hz(best) * k for k in range(1, EXPLAIN_HARM + 1)]
    return sorted(chosen)


def detect_chords(signal: np.ndarray, sr: int, dur_s: float = 0.6, detector: str = "salience") -> list[dict]:
    """One entry per attack where 2+ notes sound over dur_s. Single notes stay with notes.detect_notes."""
    if detector not in DETECTORS:
        raise ValueError(f"unknown chord detector {detector!r} ({', '.join(DETECTORS)})")
    x = np.asarray(signal, dtype=np.float64)
    span = int(round(dur_s * sr))
    pick = salience_set if detector == "salience" else _basic_pitch_picker(x, sr)
    out = []
    for a in note_onsets(x, sr):
        if a + span >= len(x):
            continue
        midis = pick(x, sr, a / sr, dur_s)
        if len(midis) >= 2:
            out.append({"start_s": a / sr, "midis": midis, "names": [midi_name(m) for m in midis]})
    return out


def _basic_pitch_picker(x: np.ndarray, sr: int):
    raise ValueError("basic-pitch detector: not implemented yet")   # replaced in Task 3
