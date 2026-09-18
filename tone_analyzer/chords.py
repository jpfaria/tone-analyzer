"""Which notes sound at one attack of ONE guitar audio, and levels at given frequencies.

Pure functions, no I/O. The level reading is the one validated for single notes
(Hann window over 0.6 s from the attack, peak within +-1.2 %, neighbourhood median
at 0.90-0.96 and 1.04-1.10 of the frequency), taken at any list of frequencies so a
chord can be read at the harmonics of each of its notes.
"""

from __future__ import annotations

import numpy as np

PEAK_TOL = 0.012
NEIGH_LO = (0.90, 0.96)
NEIGH_HI = (1.04, 1.10)


def levels_at(signal: np.ndarray, sr: int, start_s: float, freqs_hz: list[float],
              dur_s: float = 0.6) -> dict | None:
    x = np.asarray(signal, dtype=np.float64)
    ini = int(round(start_s * sr))
    n = min(int(round(dur_s * sr)), len(x) - ini)
    if n < int(0.3 * sr):
        return None
    seg = x[ini:ini + n] * np.hanning(n)
    power = np.abs(np.fft.rfft(seg, 4 * n)) ** 2
    freqs = np.fft.rfftfreq(4 * n, 1 / sr)
    level: list[float | None] = []
    neigh: list[float | None] = []
    prom: list[float | None] = []
    for f in freqs_hz:
        peak = (freqs > f * (1 - PEAK_TOL)) & (freqs < f * (1 + PEAK_TOL))
        around = (((freqs > f * NEIGH_LO[0]) & (freqs < f * NEIGH_LO[1]))
                  | ((freqs > f * NEIGH_HI[0]) & (freqs < f * NEIGH_HI[1])))
        if f > 0.9 * sr / 2 or not peak.any() or not around.any():
            level.append(None)
            neigh.append(None)
            prom.append(None)
            continue
        lv = 10.0 * np.log10(power[peak].max() + 1e-30)
        nb = 10.0 * np.log10(np.median(power[around]) + 1e-30)
        level.append(float(lv))
        neigh.append(float(nb))
        prom.append(float(lv - nb))
    return {"level_db": level, "neighbour_db": neigh, "prominence_db": prom}
