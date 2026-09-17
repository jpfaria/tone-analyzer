"""Console entry point: `tone-analyzer <command> [args...]`.

Each subcommand delegates to the module's own `main(argv)` so the argparse
surface of `analyze`, `compare`, `eq_match` and `make_correction_ir` stays the
single source of truth.
"""

from __future__ import annotations

import sys

from tone_analyzer import analyze, compare, eq_match, harmonics, make_correction_ir, separate, take, tones

_COMMANDS = {
    "analyze": analyze.main,
    "harmonics": harmonics.main,
    "take": take.main,
    "separate": separate.main,
    "tones": tones.main,
    "compare": compare.main,
    "eq-match": eq_match.main,
    "correction-ir": make_correction_ir.main,
}

USAGE = """usage: tone-analyzer <command> [args...]

commands:
  analyze        <in.wav> [--out-dir DIR]                     fingerprint.json + spectrograms + analysis.pdf
  harmonics      <in.wav> (--auto | --at SEC --midi M ...) [--out-dir DIR]  harmonics.json
  take           <in.wav> [--out-dir DIR]                     take.json: pitch, duration, saturation, noise floor
  separate       <track> [--out-dir DIR]                      guitar.wav + no_guitar.wav at 48 kHz (needs demucs)
  tones          find <song> | list | add ... | reanalyze <song>|--all   library of stored song analyses
  compare        <ref.wav> <wet.wav> [--out-dir DIR] ...      diff.json + A/B spectrogram  [obsolete: use tone-builder]
  eq-match       <ref.wav> <wet.wav> --gains g1,...,g8        next 8-band EQ gains toward the reference  [obsolete: use tone-builder]
  correction-ir  <ref.wav> <wet.wav> --output IR.wav [--taps N]  minimum-phase correction IR from the LTAS gap  [obsolete: use tone-builder]

Run `tone-analyzer <command> --help` for that command's options.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = args[0], args[1:]
    fn = _COMMANDS.get(cmd)
    if fn is None:
        print(f"tone-analyzer: unknown command '{cmd}'", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    return int(fn(rest))


if __name__ == "__main__":
    sys.exit(main())
