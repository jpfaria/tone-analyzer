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
SAL_PROM_DB = 13.0        # the method's prominence gate (validated on single notes)
SAL_HARM = 8              # harmonics read per candidate; guitar DI partials above h8 are weak and,
                          # above ~2 kHz, fall inside the COLLIDE comb of any low note anyway
MIN_FREE = 2              # the own fundamental plus one more free harmonic. Measured: a major 10th
                          # over root+fifth (G#3 in open E, C#4 in open A, F#4 in open D, A3 in
                          # barre F, D#4 in barre B) keeps only h1 and h5 free, the rest sit within
                          # COLLIDE of the lower notes' partials; 3 would drop the chord's third
FUND_FLOOR_DB = 30.0      # a fundamental this far below the strongest reading is floor, not a note.
                          # Measured on the test voicings (2 spectrum shapes): real fundamentals sit
                          # at -7.8 dB or higher; floor bumps that still pass the 13 dB prominence
                          # gate (a synthetic floor is very flat) sit at -47.9 dB or lower
MAX_NOTES = 6             # six strings
COLLIDE = 0.024           # two frequencies closer than this are the same peak: 2 x PEAK_TOL, since
                          # levels_at reads the maximum within +-PEAK_TOL of each frequency
MIDI_RANGE = range(40, 89)   # E2..E6


def _hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _explained(f: float, chosen_hz: list[float]) -> bool:
    """f lies on the harmonic comb (any k >= 1, no upper limit) of a note already chosen."""
    for f0 in chosen_hz:
        k = max(1, round(f / f0))
        if abs(f - k * f0) / f < COLLIDE:
            return True
    return False


def salience_set(signal: np.ndarray, sr: int, start_s: float, dur_s: float = 0.6) -> list[int]:
    """The octave-reduced set of notes sounding at start_s: the lowest note of each octave class.

    Candidates are walked from low to high. A candidate is a note when its own fundamental is
    prominent, within FUND_FLOOR_DB of the strongest reading, and not on the harmonic comb of a lower note already chosen, and it has at least
    MIN_FREE prominent harmonics off those combs. Walking upwards makes the argument inductive:
    every partial below a candidate's fundamental belongs to a lower note, and every lower note is
    either chosen or an octave copy of one chosen (its partials are even harmonics of that one),
    so a prominent, unexplained fundamental can only be a note of its own. Subharmonics never pass
    (their fundamental has no energy) and octave copies never pass (their fundamental is h2, h4 or
    h8 of the lower note). The comb has no upper limit so a doubling two or three octaves up is
    covered even above the lower note's last audible partial.

    Exact octave doublings are indistinguishable from the lower note alone by harmonic content,
    hence the octave reduction; the caller enumerates doublings. The same holds for a note whose
    fundamental falls within COLLIDE of a lower note's harmonic without being an octave (a twelfth,
    19 semitones, is 0.1 % off 3 x f0): it is not reported unless another note of its octave class
    lower down is.
    """
    cands = list(MIDI_RANGE)
    freqs = [_hz(m) * k for m in cands for k in range(1, SAL_HARM + 1)]
    h = levels_at(signal, sr, start_s, freqs, dur_s)
    if h is None:
        return []
    prom = h["prominence_db"]
    top = max(lv for lv in h["level_db"] if lv is not None)
    chosen: list[int] = []
    chosen_hz: list[float] = []
    for i, m in enumerate(cands):
        if len(chosen) >= MAX_NOTES:
            break
        harm = [(freqs[i * SAL_HARM + j], prom[i * SAL_HARM + j]) for j in range(SAL_HARM)]
        free = [f for f, p in harm
                if p is not None and p >= SAL_PROM_DB and not _explained(f, chosen_hz)]
        fund_db = h["level_db"][i * SAL_HARM]
        if (free and free[0] == harm[0][0] and len(free) >= MIN_FREE
                and fund_db is not None and fund_db >= top - FUND_FLOOR_DB):
            chosen.append(m)
            chosen_hz.append(_hz(m))
    return chosen


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
