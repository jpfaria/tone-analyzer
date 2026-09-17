"""The one-off importer of OpenRig evaluations into the tone library."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("importer", REPO / "scripts" / "import_openrig_evaluations.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def _eval(base: Path, name: str, title: str | None, refs: dict[str, bytes]) -> None:
    d = base / name
    (d / "refs").mkdir(parents=True)
    if title:
        (d / "eval.md").write_text(f"# {title}\n**Status:** done\n")
    for fname, payload in refs.items():
        (d / "refs" / fname).write_bytes(payload)


def test_plan_dedups_titles_roles_tracks_and_conflicts(tmp_path):
    a, b = tmp_path / "openrig", tmp_path / "appsupport"
    _eval(a, "gravity-john-mayer", "Gravity — John Mayer",
          {"lead.wav": b"L", "rhythm.wav": b"R", "guitar-demucs.wav": b"D", "original.mp3": b"M"})
    _eval(a, "john-mayer-gravity", None, {"lead.wav": b"L", "rhythm.wav": b"R"})
    _eval(a, "barao", "Bete Balanço — Barão Vermelho", {"guitars.wav": b"G", "rhythm.wav": b"G"})
    _eval(a, "heartbreak", "Heartbreak Warfare — John Mayer", {"keys.wav": b"K", "lead.wav": b"HL"})
    _eval(a, "untitled", None, {"rhythm.wav": b"U"})
    _eval(a, "no-refs", "American Idiot — Green Day", {})
    _eval(b, "streets", "Where the Streets Have No Name — U2", {"rhythm.wav": b"S2"})
    _eval(a, "streets", "Where the Streets Have No Name — U2", {"rhythm.wav": b"S1"})

    jobs, skipped = importer.plan([a, b])
    got = {(j["artist"], j["song"], j["role"], j["kind"], j["track"] is not None) for j in jobs}

    assert got == {
        ("John Mayer", "Gravity", "lead", "stem", True),
        ("John Mayer", "Gravity", "rhythm", "stem", True),
        ("John Mayer", "Gravity", "guitar-demucs", "separated", True),
        ("Barão Vermelho", "Bete Balanço", "rhythm", "stem", False),
        ("John Mayer", "Heartbreak Warfare", "lead", "stem", False),
        ("U2", "Where the Streets Have No Name", "rhythm", "stem", False),
        ("U2", "Where the Streets Have No Name", "rhythm-2", "stem", False),
    }
    reasons = " ".join(skipped)
    assert "keys.wav" in reasons and "untitled" in reasons and "no-refs" in reasons
