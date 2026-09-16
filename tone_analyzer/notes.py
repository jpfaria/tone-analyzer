"""Notes and harmonics of ONE guitar audio.

Pure functions, no I/O. Ported from the method validated against known truth
(see tone-builder spec): plain autocorrelation pitch with no octave
"correction", notes measured over 0.6 s from the attack, harmonic level read at
k*f0 with its neighbourhood median.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# The method was validated at 48 kHz, with frame and hop of 8192 / 1024 samples.
VALIDATED_SR = 48000
FRAME_S = 8192 / 48000
HOP_S = 1024 / 48000


def hz_to_midi(f_hz: float) -> float:
    return 69.0 + 12.0 * np.log2(f_hz / 440.0)


def midi_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def pitch_autocorr(
    frame: np.ndarray, sr: int, fmin: float = 70.0, fmax: float = 1400.0
) -> tuple[float, float]:
    """Plain autocorrelation pitch. Returns (f0_hz, normalized peak in 0..1).

    No octave post-processing: every variant tried lost accuracy (spec).
    The frame is brought to 48 kHz first — the rate the method was validated
    at. With integer lags at 22.05 kHz a 659 Hz period (33.46 samples) falls
    between two lags and the two-period lag wins, one octave low.
    """
    if sr != VALIDATED_SR:
        frame = resample_poly(np.asarray(frame, dtype=np.float64), VALIDATED_SR, sr)
        sr = VALIDATED_SR
    n = len(frame)
    w = frame.astype(np.float64) * np.hanning(n)
    ac = np.fft.irfft(np.abs(np.fft.rfft(w, 2 * n)) ** 2)[:n]
    ac = ac / (ac[0] + 1e-12)
    lo = max(1, int(sr / fmax))
    hi = min(n - 1, int(sr / fmin))
    k = lo + int(np.argmax(ac[lo:hi]))
    return float(sr / k), float(ac[k])


def note_onsets(
    signal: np.ndarray, sr: int, floor_rel_db: float = 30.0, min_sep_s: float = 0.5
) -> list[int]:
    """Attack sample indices: envelope rises >1.5x after a lower block."""
    x = np.asarray(signal, dtype=np.float64)
    block = max(1, int(round(1024 * sr / VALIDATED_SR)))
    if len(x) < 5 * block:
        return []
    env = np.array([np.abs(x[i:i + block]).max() for i in range(0, len(x) - block, block)])
    peak = env.max()
    if peak <= 0:
        return []
    lim = peak * 10.0 ** (-floor_rel_db / 20.0)
    out: list[int] = []
    last = -1e9
    for k in range(2, len(env) - 2):
        t = k * block / sr
        if (env[k] > lim and env[k] > env[k - 1] * 1.5
                and env[k] >= env[k + 1] * 0.8 and t - last > min_sep_s):
            out.append(k * block)
            last = t
    return out


def detect_notes(
    signal: np.ndarray,
    sr: int,
    dur_s: float = 0.6,
    conf_min: float = 0.8,
    sustain_frac: float = 0.75,
    min_estimates: int = 6,
) -> list[dict]:
    """Notes that hold one pitch over dur_s from their attack."""
    x = np.asarray(signal, dtype=np.float64)
    frame = int(round(FRAME_S * sr))
    hop = int(round(HOP_S * sr))
    span = int(round(dur_s * sr))
    found: list[dict] = []
    for a in note_onsets(x, sr):
        if a + span >= len(x):
            continue
        est = []
        f0s = []
        for k in range(0, span - frame, hop):
            f0, conf = pitch_autocorr(x[a + k:a + k + frame], sr)
            if conf > conf_min:
                est.append(int(round(hz_to_midi(f0))))
                f0s.append(f0)
        if len(est) < min_estimates:
            continue
        midi = int(np.bincount(est).argmax())
        hits = np.array(est) == midi
        if hits.mean() < sustain_frac:
            continue
        found.append({
            "start_s": a / sr,
            "midi": midi,
            "name": midi_name(midi),
            "f0_hz": float(np.median(np.array(f0s)[hits])),
        })
    return found
