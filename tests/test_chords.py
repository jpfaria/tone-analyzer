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


# A second spectrum shape: the same slope with each harmonic moved by up to +-6 dB (seeded), so
# the detector is not tuned to one smooth decay.
HARM_IRREGULAR = [h + d for h, d in zip(HARM, np.random.default_rng(7).uniform(-6.0, 6.0, len(HARM)))]


def reduce(voicing):
    """The octave-reduced set: the lowest note of each octave class stays, its octave copies go."""
    s = set(voicing)
    return sorted(m for m in s if not any(m - 12 * k in s for k in (1, 2, 3)))


def _chord_shaped(midis, harm, stagger_s=0.01, dur_s=1.5, lead_s=0.5):
    parts = []
    for i, m in enumerate(midis):
        pre = np.zeros(int(round((lead_s + i * stagger_s) * SR)), np.float32)
        parts.append(np.concatenate([pre, harmonic_note(m, SR, dur_s, harm)]))
    n = max(len(p) for p in parts)
    x = sum(np.pad(p, (0, n - len(p))) for p in parts)
    return (0.5 * x / np.abs(x).max()).astype(np.float32)


VOICINGS = {
    "E5": [40, 47],
    "E5-octave": [40, 47, 52],
    "A5-octave": [45, 52, 57],
    "D5-octave": [50, 57, 62],
    "open-E": [40, 47, 52, 56, 59, 64],
    "open-A": [45, 52, 57, 61, 64],
    "open-D": [50, 57, 62, 66],
    "open-G": [43, 47, 50, 55, 59, 67],
    "open-C": [48, 52, 55, 60, 64],
    "barre-F": [41, 48, 53, 57, 60, 65],
    "barre-B": [47, 54, 59, 63, 66],
    "Am": [45, 52, 57, 60, 64],
    "Em": [40, 47, 52, 55, 59, 64],
    "octave-A": [45, 57],
    "single-E2": [40],
    "single-E3": [52],
    "single-E4": [64],
}


@pytest.mark.parametrize("shape", ["smooth", "irregular"])
@pytest.mark.parametrize("name", list(VOICINGS))
def test_salience_finds_the_octave_reduced_chord(name, shape):
    voicing = VOICINGS[name]
    x = _chord_shaped(voicing, HARM if shape == "smooth" else HARM_IRREGULAR)
    assert chords.salience_set(x, SR, 0.5) == reduce(voicing)


@pytest.mark.parametrize("name", ["octave-A", "single-E2", "single-E3", "single-E4"])
def test_one_reduced_note_is_not_a_chord(name):
    x = _chord_shaped(VOICINGS[name], HARM)
    assert chords.detect_chords(x, SR) == []


def test_reduce_helper():
    assert reduce([45, 52, 57, 61, 64]) == [45, 52, 61]
    assert reduce([43, 47, 50, 55, 59, 67]) == [43, 47, 50]
    assert reduce([45, 57]) == [45]


def test_detect_chords_reports_attack_and_names():
    # Each chord carries an octave (E2/E3, A2/A3): detect_chords reports the octave-reduced set.
    x = np.concatenate([_chord([40, 47, 52]), _chord([45, 52, 57])])
    found = chords.detect_chords(x, SR)
    assert [c["midis"] for c in found] == [[40, 47], [45, 52]]
    assert found[0]["names"] == ["E2", "B2"]
    assert found[0]["start_s"] == pytest.approx(0.5, abs=0.03)


def test_unknown_detector_is_an_error():
    with pytest.raises(ValueError):
        chords.detect_chords(_chord([40, 47]), SR, detector="nope")
