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
    "clean_di.wav":      "06b9ada60399b47e5e60e85290bc688f696a3b017f28fc899cf936739f895120",
    "distorted_di.wav":  "7ccfdf17cec4cfee9ab110a19ea0813b4319051282e970498468fa30aba9ae9e",
    "reverb_tail.wav":   "12cc14588c3da9ff9df8617f8c2b1943c3846d79ca78cfdb5966152a9e6e1c2c",
    "delayed_echo.wav":  "83594d474cf686e5aae1c9c1a44daf08bf843060efc2f838d82377851d35c97c",
    "multi_section.wav": "e6aa3e8e7e4e3bd9b95ec2ccb0b6e2d44c5e8a1bb97362a9b50c038f038a8db3",
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
