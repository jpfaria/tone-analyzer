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
