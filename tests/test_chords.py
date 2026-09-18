"""Tests for tone_analyzer.chords — which notes sound at one attack, and levels at given frequencies."""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path

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


def _chord(midis, harm=HARM, stagger_s=0.0, dur_s=1.5, lead_s=0.5):
    parts = []
    for i, m in enumerate(midis):
        pre = np.zeros(int(round((lead_s + i * stagger_s) * SR)), np.float32)
        parts.append(np.concatenate([pre, harmonic_note(m, SR, dur_s, harm)]))
    n = max(len(p) for p in parts)
    x = sum(np.pad(p, (0, n - len(p))) for p in parts)
    return (0.5 * x / np.abs(x).max()).astype(np.float32)


# A second spectrum shape: the same slope with each harmonic moved by up to +-6 dB (seeded), so
# the detector is not tuned to one smooth decay.
HARM_IRREGULAR = [h + d for h, d in
                  zip(HARM, np.random.default_rng(7).uniform(-6.0, 6.0, len(HARM)))]


def reduce(voicing):
    """The octave-reduced set: the lowest note of each octave class stays, its octave copies go."""
    s = set(voicing)
    return sorted(m for m in s if not any(m - 12 * k in s for k in (1, 2, 3)))


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
    x = _chord(voicing, HARM if shape == "smooth" else HARM_IRREGULAR, stagger_s=0.01)
    assert chords.salience_set(x, SR, 0.5) == reduce(voicing)


@pytest.mark.parametrize("name", ["octave-A", "single-E2", "single-E3", "single-E4"])
def test_one_reduced_note_is_not_a_chord(name):
    x = _chord(VOICINGS[name], stagger_s=0.01)
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


def _fake_basic_pitch_run(rows):
    """A fake subprocess runner standing in for the basic-pitch CLI: writes the note-events CSV
    the real CLI would write (same columns, same `<stem>_basic_pitch.csv` name in the out dir)."""
    def run(args, capture_output, text):
        out_dir, wav_path = Path(args[1]), Path(args[2])
        csv_path = out_dir / f"{wav_path.stem}_basic_pitch.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start_time_s", "end_time_s", "pitch_midi", "velocity", "pitch_bend"])
            for start_s, end_s, midi in rows:
                w.writerow([start_s, end_s, midi, 100, 1])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    return run


def test_basic_pitch_finds_a_power_chord(monkeypatch):
    # basic-pitch does not octave-reduce: [40, 47, 56] (no octave), not the salience-style [40, 47, 52].
    monkeypatch.setattr(chords.shutil, "which", lambda name: "/usr/local/bin/basic-pitch")
    x = _chord([40, 47, 56])
    run = _fake_basic_pitch_run([(0.0, 3.0, 40), (0.0, 3.0, 47), (0.0, 3.0, 56)])
    found = chords.detect_chords(x, SR, detector="basic-pitch", run=run)
    assert found and found[0]["midis"] == [40, 47, 56]


def test_basic_pitch_ignores_notes_below_the_active_fraction(monkeypatch):
    monkeypatch.setattr(chords.shutil, "which", lambda name: "/usr/local/bin/basic-pitch")
    x = _chord([40, 47, 56])
    # 40 and 47 cover the whole window; 56 only a sliver of it (well under BP_ACTIVE) and 90 sits
    # outside MIDI_RANGE entirely -- neither should be picked.
    run = _fake_basic_pitch_run([(0.0, 3.0, 40), (0.0, 3.0, 47), (0.5, 0.55, 56), (0.0, 3.0, 90)])
    found = chords.detect_chords(x, SR, detector="basic-pitch", run=run)
    assert found and found[0]["midis"] == [40, 47]


def test_basic_pitch_missing_gives_install_hint(monkeypatch):
    monkeypatch.setattr(chords.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="basic-pitch not found"):
        chords.detect_chords(_chord([40, 47]), SR, detector="basic-pitch")


@pytest.mark.skipif(shutil.which("basic-pitch") is None, reason="basic-pitch CLI not installed")
def test_basic_pitch_real_cli_finds_power_chord_notes():
    x = np.concatenate([_chord([40, 47, 56]), np.zeros(SR, np.float32)])
    found = chords.detect_chords(x, SR, detector="basic-pitch")
    assert found and {40, 47, 56}.issubset(set(found[0]["midis"]))


def test_cli_chords_writes_json(tmp_path, capsys):
    import json

    import soundfile as sf

    from tone_analyzer import cli
    wav = tmp_path / "c.wav"
    sf.write(str(wav), _chord([40, 47, 56]), SR, subtype="FLOAT")
    assert cli.main(["chords", str(wav)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["detector"] == "salience"
    assert out["chords"][0]["midis"] == [40, 47, 56]


def _pink(n, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    k = np.arange(len(spec))
    k[0] = 1
    return np.fft.irfft(spec / np.sqrt(k), n)


def _strum(midis, rng, harm, max_stagger_s=0.030, residue_db=-20.0, lead_s=0.5, dur_s=1.5):
    """A real strum: each string starts at its own random offset in 0..max_stagger_s, plus pink
    noise residue residue_db under the chord's RMS over the whole signal (lead-in included, as a
    separated stem carries its residue everywhere)."""
    offs = np.sort(rng.uniform(0.0, max_stagger_s, len(midis)))
    n = int((lead_s + max_stagger_s + dur_s) * SR) + 1
    x = np.zeros(n)
    for m, o in zip(midis, offs):
        s = int(round((lead_s + o) * SR))
        v = harmonic_note(m, SR, dur_s, harm)
        x[s:s + len(v)] += v
    rms = np.sqrt(np.mean(x[int(lead_s * SR):int((lead_s + 0.6) * SR)] ** 2))
    nz = _pink(n, rng)
    x += nz * rms * 10 ** (residue_db / 20) / np.sqrt(np.mean(nz ** 2))
    return (0.5 * x / np.abs(x).max()).astype(np.float32)


def test_staggered_strums_with_residue_find_the_chord_once():
    # 60 random strums (strings 0-30 ms apart, residue 20 dB under) over the chord voicings.
    # Before chord_onsets: 25/60 first entries (11 false notes) right at the strum -- no onset at all (the rise is
    # spread over 2-3 blocks), or an onset fired in the lead-in noise whose window read the strum
    # half-way (false notes). A later entry in the beating decay repeating the same notes is
    # note_onsets' own behaviour and not a false note.
    rng = np.random.default_rng(0)
    names = [k for k, v in VOICINGS.items() if len(reduce(v)) >= 2]
    n, exact, false_notes = 60, 0, 0
    for _ in range(n):
        v = VOICINGS[names[rng.integers(len(names))]]
        x = _strum(v, rng, HARM if rng.random() < 0.5 else HARM_IRREGULAR)
        found = chords.detect_chords(x, SR)
        exact += bool(found and found[0]["midis"] == reduce(v)
                      and abs(found[0]["start_s"] - 0.5) <= 0.03)
        false_notes += sum(len(set(c["midis"]) - set(reduce(v))) for c in found)
    assert exact >= 0.95 * n
    assert false_notes == 0


def test_staggered_strum_reports_the_first_string():
    rng = np.random.default_rng(3)
    x = _strum(VOICINGS["open-E"], rng, HARM)
    found = chords.detect_chords(x, SR)
    assert found and found[0]["start_s"] == pytest.approx(0.5, abs=0.03)
