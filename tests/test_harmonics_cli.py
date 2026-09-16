"""`tone-analyzer harmonics`: harmonic levels of ONE audio, at given or detected notes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import soundfile as sf

from tests._synth import note_sequence
from tone_analyzer import cli


def _wav(tmp_path: Path) -> tuple[Path, list[float]]:
    sr = 44100
    x, starts = note_sequence([45, 57, 69], sr, 1.0, 0.5, [0.0, -6.0, -12.0, -18.0])
    p = tmp_path / "notes.wav"
    sf.write(p, x, sr, subtype="FLOAT")
    return p, starts


def test_harmonics_at_given_note(tmp_path: Path):
    wav, starts = _wav(tmp_path)
    out = tmp_path / "out"
    rc = cli.main(["harmonics", str(wav), "--at", str(starts[2]), "--midi", "69", "--out-dir", str(out)])
    assert rc == 0
    data = json.loads((out / "harmonics.json").read_text())
    assert data["schema_version"] == 1
    n = data["notes"][0]
    assert n["midi"] == 69 and n["name"] == "A4"
    assert n["relative_db"][1] == pytest.approx(-6.0, abs=0.7)
    assert len(n["level_db"]) == 16


def test_harmonics_auto_detects_notes(tmp_path: Path):
    wav, _ = _wav(tmp_path)
    out = tmp_path / "out"
    rc = cli.main(["harmonics", str(wav), "--auto", "--out-dir", str(out)])
    assert rc == 0
    data = json.loads((out / "harmonics.json").read_text())
    assert [n["midi"] for n in data["notes"]] == [45, 57, 69]


def test_harmonics_rejects_unpaired_at_midi(tmp_path: Path, capsys):
    wav, _ = _wav(tmp_path)
    rc = cli.main(["harmonics", str(wav), "--at", "1.0", "--out-dir", str(tmp_path / "o")])
    assert rc == 2
    assert "--at" in capsys.readouterr().err
