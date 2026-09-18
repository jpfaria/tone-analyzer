"""Tests for tone_analyzer.chords — which notes sound at one attack, and levels at given frequencies."""

from __future__ import annotations

import numpy as np
import pytest

from tests._synth import harmonic_note, midi_to_hz
from tone_analyzer import chords, notes

SR = 48000
HARM = [0.0, -3.0, -6.0, -9.0, -12.0, -15.0, -18.0, -21.0, -24.0, -27.0, -30.0, -33.0]


def test_levels_at_matches_harmonic_levels_on_a_single_note():
    x = np.concatenate([np.zeros(SR // 2, np.float32), harmonic_note(57, SR, 1.5, HARM)])
    f0 = midi_to_hz(57)
    h = notes.harmonic_levels(x, SR, 0.5, f0)
    lv = chords.levels_at(x, SR, 0.5, [f0 * k for k in range(1, 17)])
    assert lv["level_db"] == pytest.approx(h["level_db"])
    assert lv["prominence_db"] == pytest.approx(h["prominence_db"])


def test_levels_at_none_when_too_short():
    assert chords.levels_at(np.zeros(SR // 10), SR, 0.0, [440.0]) is None


def _chord(midis, stagger_s=0.0, dur_s=1.5, lead_s=0.5):
    parts = []
    for i, m in enumerate(midis):
        pre = np.zeros(int(round((lead_s + i * stagger_s) * SR)), np.float32)
        parts.append(np.concatenate([pre, harmonic_note(m, SR, dur_s, HARM)]))
    n = max(len(p) for p in parts)
    x = sum(np.pad(p, (0, n - len(p))) for p in parts)
    return (0.5 * x / np.abs(x).max()).astype(np.float32)


@pytest.mark.parametrize(
    "midis, expected",
    [
        ([40, 47], [40, 47]),
        ([40, 47, 52], [40, 47, 52]),
        # A2/A3 (45/57) and E3/E4 (52/64) are exact octave pairs. 61 (C#4) is not doubled and
        # survives. 45 loses to MIN_FREE: after 64, 61, 57 are chosen, 45 has only 2 free
        # harmonics left (110 Hz and 770 Hz) of the 3 required -- see task-2 report for the
        # measured per-harmonic breakdown. 57 (not 45) is the one that stays because the
        # greedy order explains 64 and 61 first, and 57 out-scores 45 in that same round.
        ([45, 52, 57, 61, 64], [52, 57, 61, 64]),
        # G2/G3/G4 (43/55/67) and B2/B3 (47/59) are octave families. 55 and 59 are fully
        # explained (every harmonic of an exact octave is an even harmonic of the lower note,
        # within EXPLAIN_HARM's k<=16 window) and never reach MIN_FREE -- 0 free harmonics
        # measured, not merely below MIN_FREE. 67 survives despite being +24 from 43: its own
        # harmonics k=7,8 (2744 Hz, 3136 Hz) sit beyond 43/47/50's k<=16 explained windows in
        # absolute Hz, so they stay free and genuinely evidence 67 rather than leak/alias.
        ([43, 47, 50, 55, 59, 67], [43, 47, 50, 67]),
    ],
)
def test_salience_finds_the_chord(midis, expected):
    x = _chord(midis, stagger_s=0.01)
    assert chords.salience_set(x, SR, 0.5) == expected


def test_single_note_is_not_a_chord():
    x = _chord([52])
    assert chords.salience_set(x, SR, 0.5) == [52]
    assert chords.detect_chords(x, SR) == []


def test_detect_chords_reports_attack_and_names():
    x = np.concatenate([_chord([40, 47, 52]), _chord([45, 52, 57])])
    found = chords.detect_chords(x, SR)
    assert [c["midis"] for c in found] == [[40, 47, 52], [45, 52, 57]]
    assert found[0]["names"] == ["E2", "B2", "E3"]
    assert found[0]["start_s"] == pytest.approx(0.5, abs=0.03)


def test_unknown_detector_is_an_error():
    with pytest.raises(ValueError):
        chords.detect_chords(_chord([40, 47]), SR, detector="nope")
