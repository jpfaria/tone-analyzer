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


def test_note_onsets_find_each_attack():
    sr = 22050
    x, starts = note_sequence([45, 57, 69], sr, note_s=1.0, gap_s=0.5, harm_db=[0.0, -6.0, -12.0])
    found = [i / sr for i in notes.note_onsets(x, sr)]
    assert len(found) == 3
    for f, s in zip(found, starts):
        assert abs(f - s) < 0.06


def test_detect_notes_names_each_note():
    sr = 44100
    x, starts = note_sequence([45, 57, 69], sr, note_s=1.0, gap_s=0.5,
                              harm_db=[0.0, -4.0, -8.0, -12.0, -16.0])
    got = notes.detect_notes(x, sr)
    assert [n["midi"] for n in got] == [45, 57, 69]
    assert [n["name"] for n in got] == ["A2", "A3", "A4"]
    assert got[2]["f0_hz"] == pytest.approx(440.0, rel=0.03)


def test_detect_notes_ignores_silence():
    sr = 22050
    assert notes.detect_notes(np.zeros(3 * sr, dtype=np.float32), sr) == []


def test_harmonic_levels_recover_known_amplitudes():
    sr = 48000
    harm = [0.0, -6.0, -12.0, -18.0, -24.0, -30.0]
    x = harmonic_note(57, sr, 1.0, harm, decay_s=50.0)
    h = notes.harmonic_levels(x, sr, 0.05, midi_to_hz(57))
    rel = h["relative_db"]
    for k, db in enumerate(harm):
        assert rel[k] == pytest.approx(db, abs=0.5)
    assert all(p >= 10.0 for p in h["prominence_db"][:len(harm)])
    assert len(h["level_db"]) == 16


def test_harmonic_absent_has_low_prominence():
    sr = 48000
    x = harmonic_note(57, sr, 1.0, [0.0, -6.0, -200.0, -12.0], decay_s=50.0)
    rng = np.random.default_rng(42)
    x = x + (rng.standard_normal(len(x)) * 1e-4).astype(np.float32)
    h = notes.harmonic_levels(x, sr, 0.05, midi_to_hz(57))
    assert h["prominence_db"][2] < 10.0
    assert h["prominence_db"][1] >= 10.0


def test_harmonic_levels_marks_above_nyquist_and_short_signal():
    sr = 22050
    x = harmonic_note(88, sr, 1.0, [0.0, -6.0])        # E6, 1319 Hz
    h = notes.harmonic_levels(x, sr, 0.05, midi_to_hz(88))
    assert h["level_db"][15] is None                  # 16*1319 Hz > 0.9 * 11025
    assert notes.harmonic_levels(x[: int(0.2 * sr)], sr, 0.0, midi_to_hz(88)) is None
