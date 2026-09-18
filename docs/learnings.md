---
tags: [tone-analyzer, learnings]
created: 2026-09-17
updated: 2026-09-18
source: claude-code-sessions
---

# tone-analyzer — Learnings

## 2026-09-18 — `basic-pitch` chord detector is BLOCKED: hard numpy conflict with tensorflow-macos

- **Gotcha / invariant:** `.venv/bin/pip install -q "basic-pitch[onnx]"` (basic-pitch 0.3.0) installs and, after two follow-up fixes (`pip install "setuptools<81"` for `resampy`'s `pkg_resources`, since setuptools ≥81 dropped it), imports fine — but only because pip silently downgraded `numpy` to 1.26.4. Reinstalling the project's pinned `numpy==2.1.3` (`pyproject.toml` line 14) then makes `from basic_pitch.inference import predict; from basic_pitch import ICASSP_2022_MODEL_PATH` fail on import with:
  ```
  ImportError: A module that was compiled using NumPy 1.x cannot be run in
  NumPy 2.1.3 as it may crash. ... numpy.core._multiarray_umath failed to import
  ```
  Root cause: basic-pitch depends on `tensorflow-macos`, which pins `numpy<2.0.0,>=1.26.0` and is imported eagerly the moment `basic_pitch.inference`/`ICASSP_2022_MODEL_PATH` is touched — even though we only asked for the ONNX runtime via `basic-pitch[onnx]`. `tensorflow-macos` and `numpy==2.1.3` cannot coexist in this venv (Python 3.12.3, macOS/arm64).
- **Why it matters:** Task 3 of issue #1 (basic-pitch as an optional chord detector) is out of scope per the brief's Step 1 gate ("sem wheel para esta versão do Python/arquitetura" — here it's a hard runtime dependency conflict, same effect: cannot install alongside the pinned numpy). Do not add `basic-pitch` to `pyproject.toml` optional-dependencies until basic-pitch drops its `tensorflow-macos` import-time dependency (or ships a build against numpy 2.x). The chord detector default stays `salience`.
- **Applies to:** `tone_analyzer/chords.py` (`_basic_pitch_picker` stays a stub that raises), `pyproject.toml` (`numpy==2.1.3` pin, `[project.optional-dependencies]`).

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
