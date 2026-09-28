"""`split` cuts a separated stereo guitar into its panned parts and labels each rhythm or lead."""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from tests._synth import harmonic_note
from tone_analyzer import split

SR = 22050
HARM = [0.0, -12.0, -20.0]
CHORDS = [[48, 52, 55], [53, 57, 60], [55, 59, 62], [48, 52, 55]]  # C F G C


def _strum(chord: list[int], dur: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = sum(harmonic_note(m, SR, dur, HARM, decay_s=4.0) * rng.uniform(0.8, 1.0) for m in chord)
    return x / np.abs(x).max() * 0.5


def _rhythm(seed: int, bars: int = 4) -> np.ndarray:
    """Chords held for the whole length; a different seed is a different take of the same part."""
    rng = np.random.default_rng(seed)
    out = []
    for b in range(bars):
        for chord in CHORDS:
            # a take never lands exactly on the other: a few ms of jitter and its own noise
            out.append(np.zeros(int(rng.uniform(0, 0.01) * SR), dtype=np.float32))
            out.append(_strum(chord, 1.0, seed * 100 + b * 10 + len(out)))
    x = np.concatenate(out)
    return x + rng.normal(0, 0.003, len(x)).astype(np.float32)


def _lead(n: int) -> np.ndarray:
    """Single notes over half the song, silence over the other half, off the chords' notes."""
    notes = [70, 73, 75, 78, 70, 73, 75, 78]
    phrase = np.concatenate([harmonic_note(m, SR, 0.5, HARM) for m in notes])
    x = np.concatenate([np.zeros(n // 2, dtype=np.float32), phrase])
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def _stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    n = min(len(left), len(right))
    return np.stack([left[:n], right[:n]], axis=1)


def test_double_tracked_rhythm_splits_into_two_rhythm_parts():
    parts = split.split_guitar(_stereo(_rhythm(1), _rhythm(2)), SR)
    assert [p["name"] for p in parts] == ["rhythm-L", "rhythm-R"]


def test_rhythm_on_one_side_and_lead_on_the_other():
    left = _rhythm(1)
    parts = split.split_guitar(_stereo(left, _lead(len(left))), SR)
    assert [p["name"] for p in parts] == ["rhythm-L", "lead-R"]


def test_centered_guitar_is_not_split():
    x = _rhythm(1)
    parts = split.split_guitar(_stereo(x, x), SR)
    assert [p["name"] for p in parts] == ["rhythm"]
    assert parts[0]["side"] == "C"


def test_centered_lead_is_labeled_lead():
    x = _lead(len(_rhythm(1)))
    parts = split.split_guitar(_stereo(x, x), SR)
    assert [p["name"] for p in parts] == ["lead"]


def test_cli_writes_part_wavs_and_split_json(tmp_path):
    src = tmp_path / "guitar.wav"
    sf.write(src, _stereo(_rhythm(1), _rhythm(2)), SR)
    out = tmp_path / "out"
    assert split.main([str(src), "--out-dir", str(out)]) == 0
    meta = json.loads((out / "split.json").read_text())
    assert [p["file"] for p in meta["parts"]] == ["rhythm-L.wav", "rhythm-R.wav"]
    for p in meta["parts"]:
        info = sf.info(str(out / p["file"]))
        assert info.samplerate == SR and info.channels == 1


def test_verdict_says_why_a_centered_guitar_was_not_split():
    x = _rhythm(1)
    v = split.verdict(_stereo(x, x), SR)
    assert v["split"] is False
    assert "center" in v["reason"]


def test_verdict_says_why_it_split():
    v = split.verdict(_stereo(_rhythm(1), _rhythm(2)), SR)
    assert v["split"] is True
    assert v["lr_correlation"] < 0.5


def test_mono_input_is_not_split():
    v = split.verdict(_rhythm(1), SR)
    assert v["split"] is False and "mono" in v["reason"]


def test_part_that_is_neither_rhythm_nor_lead_is_undetermined():
    # sustained single notes all song long: busy like rhythm, monophonic like lead
    x = np.concatenate([harmonic_note(m, SR, 1.0, HARM, decay_s=4.0) for m in [60, 62, 64, 65] * 4])
    parts = split.split_guitar(_stereo(x, x), SR)
    assert [p["role"] for p in parts] == ["undetermined"]
    assert parts[0]["name"] == "undetermined"  # never "guitar": separate writes guitar.wav in the same dir


def test_cli_on_a_centered_guitar_writes_json_that_says_it_could_not_split(tmp_path):
    src = tmp_path / "guitar.wav"
    x = _rhythm(1)
    sf.write(src, _stereo(x, x), SR)
    out = tmp_path / "out"
    assert split.main([str(src), "--out-dir", str(out)]) == 0
    meta = json.loads((out / "split.json").read_text())
    assert meta["split"] is False and meta["reason"]
    assert [p["file"] for p in meta["parts"]] == ["rhythm.wav"]
