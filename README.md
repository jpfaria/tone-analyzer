# tone-analyzer

Pure-function guitar tone analyzer. WAV in → JSON + spectrogram PNGs out.
No network, no DAW, no rig: the only side effect is files under `--out-dir`.

- **`analyze <wav>`** — `fingerprint.json` (schema 3: global + per-section
  loudness / spectrum / distortion / time-FX descriptors, honest match target),
  `spec_*.png`, `analysis.pdf`.
- **`compare <ref.wav> <wet.wav>`** — auto-picks the reference section that best
  matches the wet signal, emits `diff.json` (`proximity_pct`, `match_score`,
  ranked `recommendations[]`) plus an A/B spectrogram.
- **`eq-match <ref.wav> <wet.wav> --gains g1,…,g8`** — next 8-band EQ gains that
  move the wet render's normalised LTAS shape toward the reference.
- **`correction-ir <ref.wav> <wet.wav> --output ir.wav`** — minimum-phase
  correction IR from the LTAS gap.

## Install

```bash
pip install "tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.1.0"
tone-analyzer analyze track.wav
```

Or clone and run `./bootstrap.sh` (creates `.venv/` with an editable install).
Requires Python 3.11+ and `libsndfile` (macOS: bundled with the wheel; Debian/Ubuntu: `libsndfile1`).

## Claude plugin

```
/plugin marketplace add jpfaria/tone-analyzer
/plugin install tone-analyzer@tone-analyzer
```

The `tone-analyzer` skill bootstraps its own venv on first use and exposes the
same commands to the agent. It never touches a rig — orchestrators
(e.g. OpenRig's `openrig:tone-builder`) consume its JSON.

## Output schemas

- `fingerprint.json`: `source`, `global`, `sections[]` (each with `loudness`,
  `spectrum`, `distortion`, `time_fx`, `labels`), `fingerprint_match_target`
  (`third_octave_centers_hz`, `ltas_norm_db`, `reliable_mask`,
  `reliable_range_hz`, `top_octave_dead`, `self_floor_pct`).
- `diff.json`: `reference.matched_section_id`, `rendered`, `proximity_pct`
  (0–100, level-independent timbre; band-limited when `ref_top_octave_dead`),
  `ref_top_octave_dead`, `match_score`, `delta.*`, `recommendations[]`
  (`target`, `action`, `rationale`), `converged`. When either side's THD is
  unmeasurable (`thd_estimate_pct: null` — full mixes, sparse renders),
  `delta.thd_estimate_pct` is `null` / verdict `unavailable`, no amp
  recommendation is emitted, and `match_score` renormalises over the other terms.
- `eq-match` JSON: `new_gains[8]`, `proximity_pct`, `band_gap_db`,
  `total_gap_db`, `new_highpass_hz`, `ref_top_octave_dead`, `trustworthy_bands_hz`.

Files longer than 600 s are rejected; trim first.

## Development

```bash
./bootstrap.sh
.venv/bin/pytest -q
.venv/bin/python tests/fixtures/generate.py   # regenerate WAV fixtures (seeded)
```

## License

GPL-3.0 — see `LICENSE`.
