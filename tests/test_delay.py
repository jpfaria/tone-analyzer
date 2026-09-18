"""Delay by persistence: an echo is a copy, so the same lag shows up in independent windows.
A player's rhythm and chance do not. Known truth only: every signal here is built with a delay
we chose (or none)."""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from tests._synth import midi_to_hz
from tone_analyzer import delay

SR = 48000


def _pluck(midi: int, rng) -> np.ndarray:
    """A real string never repeats itself: random phase per harmonic, a few cents off each time."""
    t = np.arange(int(1.4 * SR)) / SR
    f0 = midi_to_hz(midi) * 2 ** (rng.uniform(-6, 6) / 1200)
    x = sum(10 ** (-rng.uniform(0, 30) / 20) * np.sin(2 * np.pi * k * f0 * t + rng.uniform(0, 2 * np.pi))
            for k in range(1, 9) if k * f0 < SR / 2)
    x = x * np.minimum(t / rng.uniform(0.002, 0.012), 1.0) * np.exp(-t / rng.uniform(0.5, 1.2)) * np.minimum((t[-1] - t) / 0.05, 1.0)   # no click at the end: identical clicks on a grid ARE copies
    pick = rng.standard_normal(len(t)) * np.exp(-t / rng.uniform(0.003, 0.01)) * rng.uniform(0.05, 0.3)   # pick noise, never the same twice
    return 0.5 * (x / np.max(np.abs(x)) + pick)


def _phrase(seconds: float = 64.0, seed: int = 3) -> np.ndarray:
    """Plucked notes on a strict 0.5 s grid (the rhythm must NOT read as an echo), pitches and
    harmonic recipes never repeated back to back, a little noise so nothing is an exact copy."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(seconds * SR))
    t, last = 0.5, None
    while t < seconds - 3.0:
        midi = int(rng.integers(45, 76))
        if midi == last:
            continue
        last = midi
        n = _pluck(midi, rng)
        i = int(t * SR)
        x[i:i + len(n)] += n * rng.uniform(0.5, 1.0)
        t += 0.5 * int(rng.integers(1, 4))
    return x + rng.standard_normal(len(x)) * 1e-4


def _echo(x: np.ndarray, ms: float, mix: float, fb: float, wow_ms: float = 0.0) -> np.ndarray:
    y, n, g = x.copy(), np.arange(len(x)), mix
    for k in range(1, 6):
        d = k * ms / 1000 * SR + k * wow_ms / 1000 * SR * np.sin(2 * np.pi * 0.7 * n / SR + k)
        src = n - d
        ok = src >= 0
        y[ok] += g * np.interp(src[ok], n, x)
        g *= fb
    return y


def test_a_known_delay_is_the_lag_most_windows_vote_for():
    r = delay.measure(_echo(_phrase(), 375.0, 0.25, 0.3), SR)
    top = r["candidates"][0]
    assert abs(top["time_ms"] - 375.0) < 1.0
    assert top["share"] >= 0.8
    assert top["spread_ms"] <= 0.3                       # a copy lands on the same sample in every window


def test_a_quiet_delay_under_a_long_second_echo_train_is_still_found():
    r = delay.measure(_echo(_phrase(), 563.0, 0.06, 0.3), SR)
    assert abs(r["candidates"][0]["time_ms"] - 563.0) < 1.0
    assert r["candidates"][0]["share"] >= 0.6


def test_a_wobbling_tape_delay_shows_up_but_with_the_spread_of_a_rhythm():
    """The known limit: a modulated delay persists, yet its lag moves between windows as much as
    a rhythmic grid does, so ONE audio cannot tell them apart. The caller must not read it as proof."""
    r = delay.measure(_echo(_phrase(), 480.0, 0.3, 0.3, wow_ms=2.0), SR)
    top = r["candidates"][0]
    assert abs(top["time_ms"] - 480.0) < 4.0 and top["share"] >= 0.6
    assert top["spread_ms"] > 0.3


def test_a_dry_phrase_on_a_strict_grid_has_no_persistent_lag():
    r = delay.measure(_phrase(), SR)
    assert r["windows"] >= 5
    # the 0.5 s grid DOES persist (unrelated attacks at the same spacing), but it wanders by ms
    assert not [c for c in r["candidates"] if c["share"] >= 0.6 and c["spread_ms"] <= 0.3]


def test_cli_writes_delay_json(tmp_path):
    wav = tmp_path / "g.wav"
    sf.write(wav, _echo(_phrase(44.0), 375.0, 0.25, 0.3).astype(np.float32), SR)
    assert delay.main([str(wav), "--out-dir", str(tmp_path / "out")]) == 0
    d = json.loads((tmp_path / "out" / "delay.json").read_text())
    assert d["schema_version"] == 1
    assert abs(d["candidates"][0]["time_ms"] - 375.0) < 1.0
    assert set(d["candidates"][0]) == {"time_ms", "windows", "share", "spread_ms", "median_strength"}
    assert "present" not in d                           # measures only: the verdict is tone-builder's
