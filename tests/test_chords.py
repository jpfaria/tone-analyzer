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
