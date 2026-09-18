"""Which notes sound at one attack of ONE guitar audio, and levels at given frequencies.

Pure functions, no I/O. The level reading is the one validated for single notes
(Hann window over 0.6 s from the attack, peak within +-1.2 %, neighbourhood median
at 0.90-0.96 and 1.04-1.10 of the frequency), taken at any list of frequencies so a
chord can be read at the harmonics of each of its notes.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

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
SAL_HARM = 8              # harmonics read per candidate. Measured over the 17 test voicings x 2
                          # spectrum shapes: 4 fails 10 cases (the major 10th's only second free
                          # harmonic is h5), 5..16 all pass with identical results; 8 keeps margin
                          # above the h5 floor without reading far into the weak upper partials
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
    prominent, within FUND_FLOOR_DB of the strongest reading, and not on the harmonic comb of a
    lower note already chosen, and it has at least MIN_FREE prominent harmonics off those combs.
    Walking upwards makes the argument inductive:
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


def detect_chords(signal: np.ndarray, sr: int, dur_s: float = 0.6, detector: str = "salience",
                   run=None) -> list[dict]:
    """One entry per attack where 2+ notes sound over dur_s. Single notes stay with notes.detect_notes.

    `run` is only used by the basic-pitch detector (injected subprocess runner, for tests).
    """
    if detector not in DETECTORS:
        raise ValueError(f"unknown chord detector {detector!r} ({', '.join(DETECTORS)})")
    x = np.asarray(signal, dtype=np.float64)
    span = int(round(dur_s * sr))
    pick = salience_set if detector == "salience" else _basic_pitch_picker(x, sr, run=run)
    out = []
    for a in note_onsets(x, sr):
        if a + span >= len(x):
            continue
        midis = pick(x, sr, a / sr, dur_s)
        if len(midis) >= 2:
            out.append({"start_s": a / sr, "midis": midis, "names": [midi_name(m) for m in midis]})
    return out


BP_ACTIVE = 0.75   # a note counts when it sounds over this fraction of the window
BP_INSTALL_HINT = (
    "basic-pitch not found — install it:\n"
    "  pipx install --python python3.11 'basic-pitch[onnx]'\n"
    "no pipx? macOS: brew install pipx && pipx ensurepath · Linux: python3 -m pip install --user pipx && pipx ensurepath\n"
    "(validated with basic-pitch 0.3.0; PyPI ships no wheel past Python 3.11 and it cannot install "
    "into this project's own venv — numpy==2.1.3 conflicts with its tensorflow-macos dependency, "
    "and even with numpy<2 pinned it needs scipy<1.13 for scipy.signal.gaussian — so it runs as a "
    "separate CLI process, same pattern as demucs in separate.py)"
)


def _basic_pitch_picker(x: np.ndarray, sr: int, run=None):
    """Run the basic-pitch CLI out of process (it cannot share this venv's numpy/scipy pins) and
    read back its note-events CSV. Not reinvented, not installed here: missing -> ValueError with
    the install hint, same pattern as demucs in separate.py.
    """
    run = run or subprocess.run
    bp = shutil.which("basic-pitch")
    if bp is None:
        raise ValueError(BP_INSTALL_HINT)

    with tempfile.TemporaryDirectory(prefix="tone-analyzer-bp-") as tmp:
        tmp_path = Path(tmp)
        wav = tmp_path / "in.wav"
        sf.write(str(wav), x.astype(np.float32), sr, subtype="FLOAT")
        proc = run([bp, tmp, str(wav), "--save-note-events", "--model-serialization", "onnx"],
                   capture_output=True, text=True)
        csv_path = tmp_path / "in_basic_pitch.csv"
        if proc.returncode != 0 or not csv_path.is_file():
            tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-20:])
            raise ValueError(f"basic-pitch failed (exit {proc.returncode}):\n{tail}")
        events: list[tuple[float, float, int]] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                events.append((float(row["start_time_s"]), float(row["end_time_s"]), int(round(float(row["pitch_midi"])))))

    def pick(_x, _sr, start_s: float, dur_s: float) -> list[int]:
        end = start_s + dur_s
        on = {m for s, e, m in events if min(e, end) - max(s, start_s) >= BP_ACTIVE * dur_s}
        return sorted(m for m in on if m in MIDI_RANGE)
    return pick


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    p = argparse.ArgumentParser(prog="tone-analyzer chords")
    p.add_argument("audio")
    p.add_argument("--detector", default="salience", choices=DETECTORS)
    p.add_argument("--out")
    a = p.parse_args(argv)
    x, sr = sf.read(a.audio, always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    try:
        found = detect_chords(x, sr, detector=a.detector)
    except ValueError as e:
        print(f"chords: {e}", file=__import__("sys").stderr)
        return 2
    text = json.dumps({"detector": a.detector, "chords": found}, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)
    return 0
