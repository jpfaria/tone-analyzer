# Tone library — design

Date: 2026-09-17 · Decision owner: jpfaria · State: approved in conversation, awaiting review of this spec.

## Why

Songs already analyzed live scattered on one machine (`~/.openrig/evaluations/`, `~/Library/Application Support/OpenRig/evaluations/`),
mixed with gear research, presets and renders, and in old fingerprint schemas (2). Another user asking
for the same song starts from zero and needs the audio again.

Two decisions from jpfaria (2026-09-16/17):

- *"eu quero colocar todos os tones que já analisei e colocar aqui no repo"* — and a lookup must search
  **this repo** and the **user's home** (`~/.tone-analyzer`) before analyzing anything.
- *"o usuário pode mandar um stem pronto; se não mandar, manda a faixa e a gente separa"* — with
  **demucs**, not reinvented: the skill asks the user to install it when missing.

## Boundary (unchanged)

tone-analyzer holds **information about one audio**. The library therefore stores **analysis only**.

| in the library (this repo) | not in the library (tone-builder) |
|---|---|
| fingerprint, harmonics, spectrograms, PDF of a song's guitar | gear research, sources, presets per device, renders, diffs |
| where the analyzed audio came from (kind, sha256, separator) | whether a tone matches, EQ, retention |

Audio **is stored** with each entry (jpfaria, 2026-09-17: *"áudio não fica fora — pq eu posso querer reprocessar as análises"*), in Git LFS. The shipped examples are ~2.5 GB of commercial recordings in a public repo: pushing them is the owner's decision.

## Entry layout

```
tones/<slug>/                         slug = <artist>-<song>, ASCII, lowercase, hyphens, leading "The" dropped
  tone.json
  track.<ext>                         the full track, when available
  <role>/                             role = rhythm | lead | guitars | acoustic | clean | …
    reference.<ext>                   the analyzed guitar audio
    fingerprint.json                  analyze output, source.path reduced to the basename
    spec_global.png  spec_notes.png  spec_section_<i>.png
    analysis.pdf
    harmonics.json                    only when the full track was available (see Flow)
```

`tone.json` (schema 1):

```json
{
  "schema_version": 1,
  "slug": "radiohead-creep",
  "artist": "Radiohead",
  "song": "Creep",
  "aliases": [],
  "roles": {
    "lead": {
      "reference": {
        "kind": "stem",                 // stem | separated | track
        "separator": null,              // "demucs 4.1.0 htdemucs_6s" when kind = separated
        "sha256": "a37dd26a5ef9…",
        "duration_s": 235.7,
        "sample_rate_hz": 44100
      },
      "track": null,                    // {sha256, duration_s, sample_rate_hz} when harmonics.json exists
      "analyzer_version": "0.2.1",
      "fingerprint_schema": 4,
      "created": "2026-09-17"
    }
  }
}
```

- `kind: stem` — the user gave an already separated guitar track (Moises, multitrack, own recording).
- `kind: separated` — we separated it from the full track with demucs.
- `kind: track` — only the full mix was analyzed (no separation possible). Marked as such; the
  numbers include the rest of the band.

**Measured fact carried over** (music-setup, *Gravity*, 2026-09-15/16): separation erases harmonics
above ~H6 (disc +21 dB over the neighbourhood where the stem reads −104 dB). So a stem **locates**
notes; harmonic **levels** are read on the full track. `harmonics.json` exists only when the track
was available, and `tone.json` says which case each role is.

Measured size: one 236 s role = 1.7 MB of analysis (13 files) plus its audio. Analysis in plain git; `*.wav|mp3|flac|aif(f)` under `tones/` in Git LFS.

## Library roots and lookup

Roots, in precedence order:

1. `~/.tone-analyzer/tones/` — the user's own analyses (written here by default).
2. `<repo>/tones/` — shipped with the plugin (`${CLAUDE_PLUGIN_ROOT}/tones`; for an editable install,
   the repo root next to the package).
3. Extra roots in `TONE_ANALYZER_TONES_PATH` (`:`-separated), searched first when set. Used by tests.

The same slug in two roots → both listed, home first.

Matching: normalize (strip accents, lowercase, drop punctuation and `the`), then compare the query
against `artist song`, `song artist`, `song` and each alias. Exact normalized match wins; otherwise
`difflib` ratio ≥ 0.8. Multiple hits → all returned, best first; the skill asks the user which.

## Commands

| command | does | writes |
|---|---|---|
| `tones find <query> [--json]` | search all roots | nothing |
| `tones list [--json]` | every entry, with roles and reference kind | nothing |
| `tones add --artist A --song S --role R --analysis DIR --reference-kind K [--reference PATH] [--track PATH] [--separator TXT] [--root DIR]` | copy `DIR` into `<root>/<slug>/<role>/`, strip `source.path`, compute sha256s, create/update `tone.json` | `<root>` (default `~/.tone-analyzer/tones`) |
| `tones reanalyze <query>\|--all [--role R]` | re-run analyze (+ harmonics on the stored track) from the stored audio | the entry |
| `separate <track> [--out-dir DIR] [--model htdemucs_6s]` | run the `demucs` CLI (`--two-stems guitar`), resample `guitar.wav` / `no_guitar.wav` to 48 kHz float | `--out-dir` |

- `tones add` refuses to overwrite an existing role unless `--replace`.
- `separate` without `demucs` on `PATH` → exit 3 and one line: `demucs not found — install it: pipx install demucs`.
  It never installs anything. demucs downloads its model on first use: `separate` is the **only**
  command that may reach the network, and only through demucs.
- 48 kHz is forced because a 44.1 kHz file read as 48 kHz shifted every note +1.5 semitone
  (music-setup, 2026-09-15).

## Flow (skill)

```
"analisa <song> [do <artist>]"
0. tones find            hit  → deliver the stored analysis (summary + PNGs); ask only if the
                                user wants it re-done with new audio
                         miss → 1
1. ask for the audio     a guitar stem, or the full track, or both
2. no stem?              which demucs || ask the user to install it (stop until they do)
                         separate <track>  → guitar.wav (kind: separated)
3. analyze <stem>        fingerprint + notes located on the stem
4. track available?      harmonics <track> --at <note.start_s> --midi <note.midi> for every note of 3
5. tones add             into ~/.tone-analyzer/tones/<slug>/<role>/
6. tell the user         where it was saved, and that it can be contributed to the repo by copying
                         the folder into tones/ — no PR opened by the skill
```

Skill iron rule 1 becomes: *no side effects outside `--out-dir`, except `tones add` writing into the
library root and `separate` letting demucs fetch its model.*

## Import of existing analyses

Sources: `~/.openrig/evaluations/*/refs/*.wav` and
`~/Library/Application Support/OpenRig/evaluations/*/refs/*.wav`.

- Deduplicate by sha256 (e.g. `gravity-john-mayer` and `john-mayer-gravity` share both refs;
  `barao-vermelho-beth-balanco` has `guitars.wav` == `rhythm.wav`).
- Artist and song come from the `# <Song> — <Artist>` heading of each `eval.md`; folders without one
  use the folder name, and the import prints them for review.
- Role = ref file name (`lead`, `rhythm`, `guitars`, `acoustic`). Non-guitar refs (`keys.wav`) are skipped.
- `kind: stem` (the refs are separated stems), `separator: null`.
- `gravity-john-mayer` also has `original.mp3`: its roles get `harmonics.json` from the track.
- Songs without refs (`green-day-american-idiot`, `-boulevard-of-broken-dreams`, `-good-riddance`,
  ampero2 `john-mayer-gravity`) are skipped and listed.
- Everything re-analyzed with the current analyzer (schema 4); old schema-2 fingerprints are not copied.
- Runs as a one-off script in `scripts/import_openrig_evaluations.py`, reading only, writing only into
  `tones/`. Expected ≈ 40 s per role. Audio is copied with each entry.
- Same slug and role with different audio (U2 *Streets*: two different rhythm takes) → the second becomes `rhythm-2`.

## Errors

| situation | behaviour |
|---|---|
| `demucs` missing | exit 3, install hint; skill asks the user, never installs |
| demucs fails | exit 1 with demucs's stderr tail; nothing written |
| `tones add` on an existing role | exit 2 unless `--replace` |
| `tones add` with an analysis dir missing `fingerprint.json` | exit 2 |
| lookup with several hits | all listed; the skill asks which |
| unwritable home root | exit 1 naming the path |

## Tests (no network, no real home)

- `tones`: slug normalization (accents, `The`, punctuation); find exact / fuzzy / miss; home precedes repo;
  `TONE_ANALYZER_TONES_PATH` honoured; `add` creates and updates `tone.json`, strips `source.path`,
  refuses overwrite without `--replace`. All roots are `tmp_path`, `HOME` monkeypatched.
- `separate`: `demucs` replaced by a fake executable on a temp `PATH` that writes 44.1 kHz stems;
  output is 48 kHz and same duration; missing demucs → exit 3; demucs non-zero → exit 1.
- CLI usage lists `tones` and `separate`.
- `test_no_network` covers `tones find/list/add`.
- Import script: run on a temp tree with two fake evaluations sharing a sha256 → one entry.

## Out of scope

- Comparing a render against a stored analysis (tone-builder).
- Gear research and presets (tone-builder).
- Opening PRs or pushing library entries.
