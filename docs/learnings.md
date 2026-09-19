---
tags: [tone-analyzer, learnings]
created: 2026-09-17
updated: 2026-09-18
source: claude-code-sessions
---

# tone-analyzer — Learnings

## 2026-09-18 — a decoded mp3 track is offset from its stem (~25 ms)

- **Gotcha / invariant:** a stem separated from an mp3, or taken from another source, can sit ~25 ms off the decoded track (encoder/decoder delay). Reading harmonics on the track at the stem's attack time then lands in the wrong place. Store the measured offset per role (`tones add --track-offset`) and read at attack + offset; `separate` decodes the track before calling demucs so new stems come out aligned.
- **Why it matters:** two library entries carried a 25 ms shift with offset 0 and silently wrong harmonics.
- **Applies to:** `tones add`, `separate`, `scripts/validate_library.py` (checks measured alignment against the stored offset and that the stem fits inside the track — a track may be longer than the stem).

## 2026-09-18 — the note detector is monophonic

- **Gotcha / invariant:** a distorted chordal rhythm part yields 0–4 notes. That is the detector's limit, not bad data; lowering the threshold invents pitch.
- **Why it matters:** do not "fix" a low note count by tuning thresholds; chords need a chord detector.
- **Applies to:** `notes`, rhythm roles in the library.

## 2026-09-18 — `basic-pitch` chord detector: cannot live in this venv, runs out of process instead

- **Gotcha / invariant:** `basic-pitch[onnx]` (0.3.0, the newest PyPI build — its classifiers only claim Python ≤3.11) cannot be installed into this project's own venv: it drags in `tensorflow-macos`, which requires `numpy<2.0.0`, while `pyproject.toml` pins `numpy==2.1.3` for the rest of the package — `from basic_pitch.inference import predict` then fails with `ImportError: numpy.core._multiarray_umath failed to import` the moment the pinned numpy is restored. Confirmed in a disposable venv (`python3.12 -m venv`, outside this repo's own `.venv`) two more incompatibilities on top: `resampy` (a basic-pitch dependency) still does `import pkg_resources`, removed from setuptools ≥81 (fix: pin `setuptools<81`); and basic-pitch's `get_pitch_bends` calls the long-removed `scipy.signal.gaussian` (fix: pin `scipy<1.13`). None of this can be reconciled with the project's own numpy/scipy pins in one venv.
- **Resolution:** basic-pitch runs **out of process**, the same pattern `tone_analyzer/separate.py` uses for demucs: `_basic_pitch_picker` in `chords.py` does `shutil.which("basic-pitch")`, writes the signal to a temp WAV, and shells out to `basic-pitch <out_dir> <wav> --save-note-events --model-serialization onnx` (verified CLI; the default model-serialization tries TensorFlow first and its SavedModel fails to load under tensorflow-macos 2.16.2 — `AttributeError: '_UserObject' object has no attribute 'add_slot'` — so ONNX must be forced explicitly). It then parses the note-events CSV basic-pitch writes to `<out_dir>/<wav_stem>_basic_pitch.csv` (header `start_time_s,end_time_s,pitch_midi,velocity,pitch_bend`; rows can carry more trailing columns than the header — from per-frame pitch-bend values — so read it with `csv.DictReader`, not fixed-width parsing). No extra in `pyproject.toml`: the CLI is installed separately by the user (`pipx install --python python3.11 'basic-pitch[onnx]'`), never inside this venv.
- **Why it matters:** the salience detector octave-reduces (`[40, 47, 52]` collapses to `[40, 47]`); basic-pitch does not — it reports the octave it actually hears (test chord `[40, 47, 56]`, no repeated octave, is the one to use). Real basic-pitch output on synthetic chords also carries spurious short-lived / off-octave notes around the true ones (observed `28`, `52`, `64`, `80` alongside a correct `[40, 47, 56]`); the `BP_ACTIVE` window-coverage gate in `pick()` filters most of that out, but a note whose predicted span happens to cover most of the picked window can still leak through — the real-CLI test only asserts the requested notes are a *subset* of what is found, and only runs when `shutil.which("basic-pitch")` succeeds (skipped otherwise, so CI without the CLI stays green).
- **Applies to:** `tone_analyzer/chords.py` (`_basic_pitch_picker`, `BP_ACTIVE`, `BP_INSTALL_HINT`), `tests/test_chords.py` (fake-subprocess tests + skip-gated real-CLI test).

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
