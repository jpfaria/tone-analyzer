---
name: tone-analyzer
description: |
  Use when the user asks to analyze a guitar audio file ("analisa esse áudio",
  "compara o som que saiu com a referência", "validar o timbre X", "fingerprint
  do som", "analyze this track", "compare these two takes"). Runs as a pure
  function: in = WAV files, out = JSON + spectrogram PNGs on disk. Handles
  multi-minute tracks (returns per-section fingerprints) and short renders
  alike. Does NOT modify any rig or project and makes no network calls.
  Orchestrators (e.g. OpenRig's tone-builder) consume this skill's JSON.
---

# tone-analyzer

Pure-function audio analyzer + A/B comparator. Callers consume the JSON output
to adjust their signal chain; this skill itself never mutates anything outside
`--out-dir`.

## Iron rules

1. **No side effects outside `--out-dir`.** No MCP calls, no rig edits, no
   project writes, no `$HOME` caches — every chain touch is the caller's job.
   No stdout chatter beyond a single line announcing the out-dir.
2. **No name claims from audio.** "It sounds like a Mesa Rectifier" is
   research, not measurement — never claim it from audio. `gain_character`
   is a four-bucket enum, not a model name.
3. **No playing-technique claims.** Never label a take "palm-muted",
   "gallop", "fingerpicked", "sweep-picked", "tremolo-picked" — the
   fingerprint does not measure technique, and a song's/artist's
   reputation is not evidence. Describe only what the analyzer reports
   (`dynamics_profile`, crest factor, transient density) or what is
   directly visible in the spectrogram. If you infer from a signal, make
   the chain explicit ("crest 15 dB ⇒ gaps between hits"), never jump to
   a named technique.
4. **Heuristic section labels only.** Sections are tagged with
   `tone_profile + dynamics_profile + presence`. Never `verse`, `chorus`,
   `bridge`, `solo` as labels — that requires music-theoretic structure
   this analyzer doesn't measure.
5. **`match_score` is a technical distance.** When surfacing it in chat,
   say so explicitly — e.g. "technically 0.71 — this is a measured
   distance, not a measure of how close it sounds to a human ear."
   *(Render in the user's language at runtime; this English example
   documents the framing, not the literal words.)*
6. **English in code, comments, JSON, summaries.** Chat with the user stays
   in their language; everything persisted to disk is English.

## Prerequisites

```bash
which ffmpeg                            # required for non-PCM decode fallback
python3 --version                       # must be ≥ 3.11
```

If either fails, stop and tell the user what to install.

## First-run bootstrap

```bash
"${CLAUDE_PLUGIN_ROOT}/bootstrap.sh"    # idempotent; <1 s on subsequent runs
```

The venv lives at `${CLAUDE_PLUGIN_ROOT}/.venv` (gitignored). Outside a
plugin install, `CLAUDE_PLUGIN_ROOT` is the repo root. The bootstrap stamps
the `pyproject.toml` hash so it knows when to reinstall.

## Workflow

1. **Decide the mode** from how many WAV files the user gave you:
   - 1 file → **analyze**.
   - 2 files → **compare** (first = reference, second = wet/rendered).
   - 2 files + current EQ gains → **eq-match** (auto-EQ-match: compute the
     next 8-band gains that move the wet render's spectral SHAPE toward the
     reference; used by an orchestrator's EQ loop).
2. **Run it:**
   ```bash
   TA="${CLAUDE_PLUGIN_ROOT}/.venv/bin/tone-analyzer"
   "$TA" analyze <input.wav> [--out-dir DIR]
   # or
   "$TA" compare <ref.wav> <wet.wav> [--out-dir DIR] [--ref-section IDX] [--wet-section IDX]
   # or (auto-EQ-match)
   "$TA" eq-match <ref.wav> <wet.wav> --gains <g1,…,g8> [--hp-hz HZ] [--output FILE]
   ```
   `analyze`/`compare` print the resolved out-dir on the last line.

   **`eq-match`** is a PURE measurement+arithmetic step (no rig, no
   network, no render): it emits `new_gains` (8 absolute EQ gains, dB),
   **`proximity_pct`** (the acceptance bar), `band_gap_db`, `total_gap_db`,
   and `new_highpass_hz`. All are computed from the **level-normalised
   LTAS** over signal-bearing windows (silence trimmed < -45 dB, level
   removed, sampled at the 8 `eq_eight_band_parametric` octave centres) —
   so loudness is never matched. **`proximity_pct`** (0–100) is the
   level-independent timbre number: cosine similarity of the
   mean-subtracted per-band LTAS vectors, 100 = identical envelope shape.
   It is the number an orchestrator gates on (≥ 95); `total_gap_db` is a
   raw dB diagnostic only. **Dead-top guard:** when the reference's top
   octave is an AI source-separation artifact (highest band ≥ 25 dB below
   the low/mid body — no real amp+cab is that dark), the bands ≥ ~5 kHz are
   **excluded** from `proximity_pct`, the gap, AND the returned `new_gains`
   (so the loop never low-passes the render to chase a dead top), and
   **`ref_top_octave_dead: true`** + `trustworthy_bands_hz` are emitted.
   This stops the "99 % but sounds muffled" result a full-band cosine
   produces when the artifact band dominates the vector. The caller feeds
   the EQ's current gains in, applies `new_gains`, re-renders, and loops
   until `proximity_pct ≥ 95`. Honest ceiling: a generic-DI render vs a
   real recording cannot reach 100 (note content differs) — the target is
   spectral shape, not bit-exactness.

   **`--out-dir`.** Callers pass an absolute directory they own. When
   omitted the script falls back to `/tmp/tone-analyzer/<unix_ts>/` so a
   one-shot manual run still works.

   `--wet-section` accepts an int index (pin a specific wet section) or the
   literal `auto` (opt into the smarter auto-pick that skips silent background
   sections). Omitted = section 0 (backward-compatible default).
3. **Read the PNGs as visual evidence.** Use the Read tool on each
   `spec_*.png` or `ab_spec.png`. They're real images and you can see them.
4. **Summarize in chat:**
   - **analyze**: one short paragraph per section — gain character,
     dynamics, presence, and any notable time-FX (delay/reverb estimates).
     Mention the `spec_global.png` for the full overview.
   - **compare**: lead with **`proximity_pct`** (the level-independent
     timbre number, 0–100 — an orchestrator's acceptance bar), then
     `match_score` (and the caveat from iron rule 5 — it folds in
     level/onsets/silence, so it is NOT the timbre bar), then the matched
     section ID + reason, then the top 2-3 recommendations as one sentence
     each.
5. **Stop at the diff.** Adjusting a chain is the caller's job.

## Long files

Files > 600 s are rejected with `"file too long (max 600 s): <path>, got X s"`.
If the user has a long track, ask them to trim it first (e.g., to the chorus
or to a specific minute range) before re-running.

## Anti-patterns

- ❌ Calling any rig/MCP tool because "it would be faster to also adjust the chain."
- ❌ Claiming `match_score = 0.95` means "sounds identical to a human." It's
  a weighted technical distance.
- ❌ Inventing music-theoretic section names. Use the tag triple as-is.
- ❌ Writing to anywhere outside `--out-dir`. No exceptions.
- ❌ Naming the amp/pedal model from audio alone.
- ❌ Computing or guessing `output_gain_db` for any block — not this skill's
  concern.

## Output schemas

See `README.md` (Output schemas). Short form:

- `fingerprint.json` (schema 3): `source`, `global`, `sections[]` (each with
  `loudness`, `spectrum`, `distortion`, `time_fx`, `labels`),
  `fingerprint_match_target`.
- `analysis.pdf`: human-readable report emitted by `analyze` alongside
  the JSON + PNGs. Multi-page, landscape letter: (1) cover with source
  metadata + global LUFS/peak/stereo, (2) full-track mel spectrogram with
  section boundaries, (3+) one page per section showing labels / loudness
  / spectrum / distortion / time_fx + band-energy table + the section's
  mel spectrogram. Hand this to the user when they ask for the analysis
  in a single document. Filename is fixed (`analysis.pdf`) so callers
  can find it deterministically; lives in the same `--out-dir` as the
  JSON.
- `diff.json`: `reference.matched_section_id`, `rendered`,
  `proximity_pct` (level-independent timbre %, 0–100 — an orchestrator's
  acceptance bar; band-limited to the trustworthy range when
  `ref_top_octave_dead`), `ref_top_octave_dead` (bool — separated-stem dead
  top octave detected, bands ≥ ~5 kHz excluded), `match_score`,
  `delta.*`, `recommendations[]` (priority-sorted, each with `target`,
  `action`, `rationale`), `converged`.

## When something looks off

If section counts seem clearly wrong on a real track (e.g., a riff is split
into 8 sections, or a 4-minute song is reported as 1 section), say so to
the user. The segmentation `k = ceil(duration_s / 30)` heuristic is
deliberately conservative — bug reports from real usage are how it gets
better.

When the wet is a render through a DI that has a silent intro (a common
case with a bundled DI `input.wav`), the wet's `section_0` will be
silence — auto-comparison against that biases the diff. Pin
`--wet-section IDX` to the section that carries the target tone
character (run `analyze wet.wav` first to see the sections).
