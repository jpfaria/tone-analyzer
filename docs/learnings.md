---
tags: [tone-analyzer, learnings]
created: 2026-09-17
updated: 2026-09-17
source: claude-code-sessions
---

# tone-analyzer — Learnings

## 2026-09-17 — demucs `htdemucs_6s` dies on Apple MPS: force `-d cpu`

- **Gotcha / invariant:** on a Mac, demucs picks the MPS GPU and `htdemucs_6s` crashes on an unsupported op. `PYTORCH_ENABLE_MPS_FALLBACK=1` does NOT fix it; `demucs -d cpu` does (~1.5–2 min per song).
- **Why it matters:** `separate` in v0.3.0 does not pin the device, so it fails on every Mac. Fixed in 0.3.1 (`9e44bf6`, on main); anything pinned to v0.3.0 still has the bug.
- **Applies to:** `tone_analyzer/separate.py`. Working install: `uv tool install demucs --python 3.12 --with torch==2.5.1 --with torchaudio==2.5.1 --with soundfile` (demucs 4.1.0).

## 2026-09-17 — A demucs stem locates notes; it does not measure them

- **Gotcha / invariant:** Gravity, 46 notes, stem vs full track (harmonics ≥ 10 dB prominent on the track): H2–H6 median +0–3 dB but 6–13 dB typical per-note error; H7–H16 up to −16 dB (stem darker), 10–18 dB per-note error. All 46 notes were still found on the stem.
- **Why it matters:** harmonic levels must come from the full track; a stem-only entry is `reference.kind: stem` and degraded.
- **Applies to:** `harmonics`, `tones add`, the skill's stem step.

## 2026-09-17 — Effect detectors fail on known truth

- **Gotcha / invariant:** `detect_delay`, `estimate_rt60_s` and `classify_gain_character` were run on renders with known chains: clean came out "distortion", a dry case got RT60 3.15 s at confidence 0.8 (it measures string sustain), delay came out random (rhythm fools envelope correlation). A cepstrum delay detector voted by persistence over independent 20 s windows found the true delay within 1 ms, also on a real mix.
- **Why it matters:** do not trust these fields for "is there delay/reverb/drive?" until they pass a known-truth test.
- **Applies to:** `analyze` time-FX and gain fields. Details: tone-builder `docs/pesquisa/2026-09-17-deteccao-de-efeitos.md`.
