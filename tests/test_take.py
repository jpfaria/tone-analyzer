"""`take`: metrics of ONE recorded take. Measures only; accepting a take is tone-builder's call."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from tests._synth import harmonic_note
from tone_analyzer import cli, take


def test_saturated_samples_counts_every_channel():
    left = np.zeros(1000, dtype=np.float32)
    right = np.zeros(1000, dtype=np.float32)
    right[10:13] = 1.0
    stereo = np.stack([left, right])          # mono mixdown would peak at 0.5
    assert take.saturated_samples(stereo) == 3
    assert take.saturated_samples(left) == 0


def _take(sr: int, midi: int, pre_s: float, noise: float, gain: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(42)
    pre = (rng.standard_normal(int(pre_s * sr)) * noise).astype(np.float32)
    note = harmonic_note(midi, sr, 0.9, [0.0, -6.0, -12.0]) * gain
    note = note + (rng.standard_normal(len(note)) * noise).astype(np.float32)
    return np.concatenate([pre, note]).astype(np.float32)


def test_take_metrics_clean_note():
    sr = 48000
    m = take.take_metrics(_take(sr, 57, 0.05, 1e-4), sr)
    assert m["midi"] == 57 and m["name"] == "A3"
    assert m["saturated_samples"] == 0
    assert m["snr_db"] > 30.0
    assert abs(m["onset_s"] - 0.05) < 0.03
    assert abs(m["duration_s"] - 0.95) < 0.01


def test_take_metrics_clipped_note():
    sr = 48000
    x = np.clip(_take(sr, 57, 0.05, 1e-4, gain=4.0), -1.0, 1.0)
    assert take.take_metrics(x, sr)["saturated_samples"] > 0


def test_take_metrics_silence_has_no_pitch():
    sr = 48000
    m = take.take_metrics(np.zeros(sr, dtype=np.float32), sr)
    assert m["midi"] is None and m["name"] is None


def test_take_cli_writes_json(tmp_path: Path):
    sr = 48000
    wav = tmp_path / "c5-45-A2.wav"
    sf.write(wav, _take(sr, 45, 0.05, 1e-4), sr, subtype="FLOAT")
    out = tmp_path / "out"
    assert cli.main(["take", str(wav), "--out-dir", str(out)]) == 0
    data = json.loads((out / "take.json").read_text())
    assert data["midi"] == 45
    assert "ok" not in data            # measuring only — no verdict here


def test_take_metrics_library_layout_20ms_preroll():
    """Library notes start ~20 ms before the attack — less than one onset block.

    Regression: with 50 ms of pre-roll the synthetic test passed while the real
    library scored 3/96, because the envelope-rise onset detector never saw the
    rise inside the first block.
    """
    sr = 48000
    for midi in (40, 52, 64, 76):
        m = take.take_metrics(_take(sr, midi, 0.02, 1e-4), sr)
        assert m["midi"] == midi
        assert abs(m["onset_s"] - 0.02) < 0.01
        assert m["snr_db"] is not None and m["snr_db"] > 30.0
