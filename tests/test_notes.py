"""Tests for tone_analyzer.notes — one audio in, notes and harmonics out."""

from __future__ import annotations

import numpy as np
import pytest

from tests._synth import harmonic_note, midi_to_hz, note_sequence


def test_synth_note_has_requested_fundamental():
    sr = 22050
    x = harmonic_note(69, sr, 1.0, [0.0, -6.0, -12.0])
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    assert abs(freqs[np.argmax(spec)] - 440.0) < 2.0
    assert x.dtype == np.float32
    assert np.abs(x).max() <= 1.0


def test_synth_sequence_reports_starts():
    sr = 22050
    x, starts = note_sequence([45, 57, 69], sr, note_s=1.0, gap_s=0.5, harm_db=[0.0, -6.0])
    assert starts == pytest.approx([0.5, 2.0, 3.5])
    assert len(x) == int(round(5.0 * sr))
    assert abs(midi_to_hz(69) - 440.0) < 1e-9


from tone_analyzer import notes


@pytest.mark.parametrize("sr", [22050, 44100, 48000])
@pytest.mark.parametrize("midi", [40, 45, 52, 57, 64, 69, 76])
def test_pitch_autocorr_finds_midi(sr, midi):
    x = harmonic_note(midi, sr, 1.0, [0.0, -4.0, -8.0, -12.0, -16.0, -20.0])
    frame = x[int(0.1 * sr):int(0.1 * sr) + int(round(0.171 * sr))]
    f0, conf = notes.pitch_autocorr(frame, sr)
    assert round(notes.hz_to_midi(f0)) == midi
    assert conf > 0.8


def test_midi_name():
    assert notes.midi_name(69) == "A4"
    assert notes.midi_name(60) == "C4"
    assert notes.midi_name(40) == "E2"
