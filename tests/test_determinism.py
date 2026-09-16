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
    "clean_di.wav":      "e5a966d833e23bf3e5e7d92ffc877482ba141571e8f8b4dc1db8c1b1bda5ce2d",
    "distorted_di.wav":  "e891b7cb5635ce7d1da1b00345c7f5e7bc575e14aec351a10b0091e264f8b901",
    "reverb_tail.wav":   "05cfb26262b9e2c84821c07208fe783f3fbc4c9e172a3f02d5e262bf34041bde",
    "delayed_echo.wav":  "9b0121479b67131d4a9e784a868554d6e95bf6c97513f17c2b7d7addb6f0379e",
    "multi_section.wav": "58cd91fa236e1251df8b0656b1c6ae8ea913ff16bf58ef64021e8026c2673570",
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
