# tone-analyzer

Extracts information from ONE guitar audio: metrics (JSON), documentation (PDF)
and spectrum (PNG). No network, no DAW, no rig: the only side effect is files
under `--out-dir`. Comparing two audios or deciding whether a tone matches
belongs to [tone-builder](https://github.com/jpfaria/tone-builder).

- **`analyze <wav>`** — `fingerprint.json` (schema 4: global incl. per-channel
  `saturated_samples`, per-section loudness / spectrum / distortion / time-FX,
  detected `notes[]` with harmonic levels), `spec_*.png` incl. `spec_notes.png`,
  `analysis.pdf` incl. a Notes page.
- **`harmonics <wav> (--auto | --at SEC --midi M …)`** — harmonics H1..H16 of a
  note at a given attack time (e.g. inside a full mix) or of the detected notes.
- **`take <wav>`** — one recorded note: pitch, onset, duration, saturated
  samples, noise floor, SNR. Measures only; no verdict.
- **`delay <wav>`** — echo lags ranked by how many independent 20 s windows vote for them, with
  the spread of the lag across windows (a copy: 0.00–0.05 ms; a rhythmic grid: 0.5–2 ms; a wobbling
  tape delay looks like a rhythm — one audio cannot tell). Measures only; no verdict.
- **`separate <track>`** — guitar out of a full mix with [demucs](https://github.com/adefossez/demucs)
  (`pipx install --python python3.12 demucs`, not bundled; no pipx → `brew install pipx`): `guitar.wav`, `no_guitar.wav`, 48 kHz.
- **`tones find|list|add|reanalyze`** — the song library (below).
- **Obsolete** (they compare two audios — use tone-builder): `compare`,
  `eq-match`, `correction-ir`.

## Install

```bash
pip install "tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.2.1"
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
(tone-builder) consume its JSON.

## Song library

Songs already analyzed are stored so nobody analyzes them twice. Lookup order:
`$TONE_ANALYZER_TONES_PATH`, `~/.tone-analyzer/tones/` (your own), then `tones/` in
this repo (shipped as examples).

```
tones/<artist>-<song>/
  tone.json                 artist, song, per role: reference kind (stem|separated|track), sha256, analyzer version
  track.<ext>               the full track, when available (harmonic levels are read on it)
  <role>/                   lead, rhythm, acoustic, …
    reference.<ext>         the analyzed guitar audio
    fingerprint.json  harmonics.json  analysis.pdf  spec_*.png
```

```bash
tone-analyzer tones find creep
tone-analyzer tones add --artist Radiohead --song Creep --role lead --analysis OUT --reference-kind stem --reference lead.wav
tone-analyzer tones reanalyze --all        # after an analyzer change, from the stored audio
```

When a stem and its track do not start at the same instant (an mp3 decoder delay is
typically 25 ms), store the difference with `tones add --track-offset SECONDS`; harmonics
are read at attack + offset. `scripts/validate_library.py` re-checks every entry: audio
hashes, schema, track length, measured alignment against the stored offset, one harmonics
row per note.

Audio in `tones/` is stored with Git LFS (`git lfs install` before cloning).
Separated stems locate notes; harmonic levels are read on the full track, because
separation erases harmonics above ~H6.

## Output schemas

- `fingerprint.json` (schema 4): `source`, `global` (`lufs_integrated`, `peak_db`,
  `saturated_samples`, `stereo`), `sections[]` (`loudness`, `spectrum`,
  `distortion`, `time_fx`, `labels`), `notes[]` (`start_s`, `midi`, `name`,
  `f0_hz`, `level_db[16]`, `neighbour_db[16]`, `prominence_db[16]`,
  `relative_db[16]`). `peak_db` is a mono mixdown — read `saturated_samples`
  to know whether any channel clipped.
- `harmonics.json` (schema 1): `source`, `notes[]` as above.
- `take.json`: `duration_s`, `onset_s`, `midi`, `name`, `f0_hz`,
  `pitch_confidence`, `saturated_samples`, `peak_db`, `noise_floor_db`,
  `signal_db`, `snr_db`.

Files longer than 600 s are rejected; trim first.

## Development

```bash
./bootstrap.sh
.venv/bin/pytest -q
.venv/bin/python tests/fixtures/generate.py   # regenerate WAV fixtures (seeded)
```

## License

GPL-3.0 — see `LICENSE`.
