"""Pinned-hash tests: fingerprint.json must be byte-identical across runs.

The hash covers the JSON re-serialised with `source.path` removed — the
absolute input path is the ONE field that legitimately differs per machine
and would otherwise pin the test to whoever last ran it.

If a code change perturbs any pinned hash, update it here in the same commit
with a one-line justification in the commit body. The hash assertion is what
catches accidental numerical drift; the dictionary structure of the JSON is
covered by test_analyze.py.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tone_analyzer import analyze

PINNED_HASHES = {
    "clean_di.wav":      "e48fde683261d5d6f150f53374069fbaa58a9bd6624374f93f5faf654d82085e",
    "distorted_di.wav":  "14fa719aef85c8b79d5f06796e184457e89106dee7a1ae332b2e20a2ca000595",
    "reverb_tail.wav":   "78f5dd28fc7e040f5563895ddea74f5fe3dd6b01e6e9ba26a8f23087f105e005",
    "delayed_echo.wav":  "dd985c9fbdd744729b27d4d5a9de3a292bd4393140004f346b25bc30a91406cf",
    "multi_section.wav": "1a7034ede89ddc1878480645fbf58667c1aa4e2ca09953917f8e2ac12b4189de",
}


@pytest.fixture(autouse=True)
def clear_analyzer_cache() -> None:
    """The /tmp cache used by compare.py mustn't influence analyze's output —
    but if a prior compare run left stale entries, clearing them eliminates
    any chance of confusion."""
    cache = Path("/tmp/tone-analyzer-cache")
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)


def _portable_hash(fp_path: Path) -> str:
    """sha256 of the fingerprint with the machine-specific `source.path` dropped."""
    data = json.loads(fp_path.read_text())
    data["source"] = {k: v for k, v in data["source"].items() if k != "path"}
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("fixture_name,expected_hash", list(PINNED_HASHES.items()))
def test_fingerprint_hash_pinned(fixture_name: str, expected_hash: str, fixtures_dir: Path, tmp_path: Path) -> None:
    fixture_path = fixtures_dir / fixture_name
    out_dir = tmp_path / "out"
    rc = analyze.main([str(fixture_path), "--out-dir", str(out_dir)])
    assert rc == 0
    fp_path = out_dir / "fingerprint.json"
    actual = _portable_hash(fp_path)
    assert actual == expected_hash, (
        f"Determinism drift on {fixture_name}: expected {expected_hash}, got {actual}. "
        "If this drift is intentional, update PINNED_HASHES with a one-line "
        "justification in the commit body."
    )
