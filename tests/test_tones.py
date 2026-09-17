"""Tone library: stored analyses per song, looked up in several roots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tone_analyzer import tones


def _analysis_dir(tmp_path: Path, name: str = "an") -> Path:
    d = tmp_path / name
    d.mkdir()
    fp = {"schema_version": 4, "source": {"path": "/Users/someone/secret/lead.wav", "sha256": "abc"}}
    (d / "fingerprint.json").write_text(json.dumps(fp))
    (d / "spec_global.png").write_bytes(b"png")
    return d


def _audio(tmp_path: Path, name: str, payload: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(payload)
    return p


@pytest.mark.parametrize(
    "artist,song,slug",
    [
        ("Radiohead", "Creep", "radiohead-creep"),
        ("Barão Vermelho", "Bete Balanço", "barao-vermelho-bete-balanco"),
        ("The Outfield", "Your Love", "outfield-your-love"),
        ("CPM 22", "Um Minuto Para o Fim do Mundo", "cpm-22-um-minuto-para-o-fim-do-mundo"),
        ("Pink Floyd", "Another Brick in the Wall, Pt. 2", "pink-floyd-another-brick-in-the-wall-pt-2"),
        ("Silverchair", "Israel's Son", "silverchair-israels-son"),
        ("Guns N’ Roses", "Don’t Cry", "guns-n-roses-dont-cry"),
    ],
)
def test_slug_is_ascii_lowercase_hyphenated(artist, song, slug):
    assert tones.slug(artist, song) == slug


def test_add_creates_entry_and_strips_local_path(tmp_path):
    root = tmp_path / "lib"
    ref = _audio(tmp_path, "lead.wav", b"stem")
    entry = tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path), "stem", reference=ref)

    assert entry == root / "radiohead-creep"
    meta = json.loads((entry / "tone.json").read_text())
    assert meta["artist"] == "Radiohead" and meta["song"] == "Creep"
    role = meta["roles"]["lead"]
    assert role["reference"]["kind"] == "stem"
    assert len(role["reference"]["sha256"]) == 64
    assert role["track"] is None
    assert role["fingerprint_schema"] == 4
    fp = json.loads((entry / "lead" / "fingerprint.json").read_text())
    assert fp["source"]["path"] == "lead.wav"
    assert (entry / "lead" / "spec_global.png").is_file()


def test_add_second_role_keeps_first(tmp_path):
    root = tmp_path / "lib"
    tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path, "a"), "stem")
    tones.add(root, "Radiohead", "Creep", "rhythm", _analysis_dir(tmp_path, "b"), "stem")
    meta = json.loads((root / "radiohead-creep" / "tone.json").read_text())
    assert sorted(meta["roles"]) == ["lead", "rhythm"]


def test_add_existing_role_refuses_without_replace(tmp_path):
    root = tmp_path / "lib"
    tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path, "a"), "stem")
    with pytest.raises(tones.LibraryError):
        tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path, "b"), "stem")
    tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path, "c"), "stem", replace=True)


def test_add_requires_fingerprint(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(tones.LibraryError):
        tones.add(tmp_path / "lib", "A", "B", "lead", empty, "stem")


def test_add_rejects_unknown_kind(tmp_path):
    with pytest.raises(tones.LibraryError):
        tones.add(tmp_path / "lib", "A", "B", "lead", _analysis_dir(tmp_path), "mp3")


def test_add_records_track_when_given(tmp_path):
    root = tmp_path / "lib"
    track = _audio(tmp_path, "song.mp3", b"mix")
    tones.add(root, "John Mayer", "Gravity", "lead", _analysis_dir(tmp_path), "separated",
              track=track, separator="demucs 4.1.0 htdemucs_6s")
    role = json.loads((root / "john-mayer-gravity" / "tone.json").read_text())["roles"]["lead"]
    assert role["reference"]["separator"] == "demucs 4.1.0 htdemucs_6s"
    assert len(role["track"]["sha256"]) == 64


@pytest.fixture
def two_roots(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    tones.add(home, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path, "a"), "stem")
    tones.add(repo, "Radiohead", "Creep", "rhythm", _analysis_dir(tmp_path, "b"), "stem")
    tones.add(repo, "John Mayer", "Gravity", "lead", _analysis_dir(tmp_path, "c"), "stem")
    return [home, repo]


@pytest.mark.parametrize("query", ["creep", "Radiohead Creep", "creep radiohead", "CRÉEP", "radiohed creep"])
def test_find_matches_exact_and_fuzzy(two_roots, query):
    hits = tones.find(query, two_roots)
    assert hits and hits[0]["slug"] == "radiohead-creep"


def test_find_lists_home_before_repo(two_roots):
    hits = [h for h in tones.find("creep", two_roots) if h["slug"] == "radiohead-creep"]
    assert [h["root"] for h in hits] == [str(r) for r in two_roots]


def test_find_miss_returns_empty(two_roots):
    assert tones.find("smells like teen spirit", two_roots) == []


def test_list_every_entry(two_roots):
    slugs = sorted(e["slug"] for e in tones.list_entries(two_roots))
    assert slugs == ["john-mayer-gravity", "radiohead-creep", "radiohead-creep"]


def test_default_roots_env_then_home_then_repo(tmp_path, monkeypatch):
    extra = tmp_path / "extra"
    monkeypatch.setenv("TONE_ANALYZER_TONES_PATH", str(extra))
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    roots = tones.default_roots()
    assert roots[0] == extra
    assert roots[1] == tmp_path / "h" / ".tone-analyzer" / "tones"
    assert roots[2].name == "tones"


def test_cli_add_then_find_json(tmp_path, capsys, monkeypatch):
    lib = tmp_path / "lib"
    monkeypatch.setenv("TONE_ANALYZER_TONES_PATH", str(lib))
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    rc = tones.main(["add", "--artist", "Radiohead", "--song", "Creep", "--role", "lead",
                     "--analysis", str(_analysis_dir(tmp_path)), "--reference-kind", "stem",
                     "--root", str(lib)])
    assert rc == 0
    capsys.readouterr()
    assert tones.main(["find", "creep", "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]["slug"] == "radiohead-creep"
    assert hits[0]["roles"] == ["lead"]


def test_cli_find_miss_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("TONE_ANALYZER_TONES_PATH", str(tmp_path / "lib"))
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert tones.main(["find", "nothing here at all"]) == 1


def test_cli_add_existing_role_exits_2(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    args = ["add", "--artist", "A", "--song", "B", "--role", "lead",
            "--analysis", str(_analysis_dir(tmp_path)), "--reference-kind", "stem", "--root", str(lib)]
    assert tones.main(args) == 0
    assert tones.main(args) == 2


# --------------------------------------------------------------------------- stored audio


def test_add_stores_reference_audio_in_role(tmp_path):
    root = tmp_path / "lib"
    ref = _audio(tmp_path, "lead.wav", b"stem")
    entry = tones.add(root, "Radiohead", "Creep", "lead", _analysis_dir(tmp_path), "stem", reference=ref)
    assert (entry / "lead" / "reference.wav").read_bytes() == b"stem"
    meta = json.loads((entry / "tone.json").read_text())
    assert meta["roles"]["lead"]["reference"]["file"] == "lead/reference.wav"


def test_add_stores_track_once_per_song(tmp_path):
    root = tmp_path / "lib"
    track = _audio(tmp_path, "song.mp3", b"mix")
    entry = tones.add(root, "John Mayer", "Gravity", "lead", _analysis_dir(tmp_path, "a"), "stem", track=track)
    assert (entry / "track.mp3").read_bytes() == b"mix"
    meta = json.loads((entry / "tone.json").read_text())
    assert meta["roles"]["lead"]["track"]["file"] == "track.mp3"


def test_replace_without_new_reference_keeps_stored_audio(tmp_path):
    root = tmp_path / "lib"
    ref = _audio(tmp_path, "lead.wav", b"stem")
    tones.add(root, "A", "B", "lead", _analysis_dir(tmp_path, "a"), "stem", reference=ref)
    entry = tones.add(root, "A", "B", "lead", _analysis_dir(tmp_path, "b"), "stem", replace=True)
    assert (entry / "lead" / "reference.wav").read_bytes() == b"stem"
    meta = json.loads((entry / "tone.json").read_text())
    assert meta["roles"]["lead"]["reference"]["file"] == "lead/reference.wav"
    assert len(meta["roles"]["lead"]["reference"]["sha256"]) == 64


def _note_wav(path: Path) -> Path:
    import soundfile as sf

    from tests._synth import note_sequence

    x, _ = note_sequence([45, 57], 48000, 1.0, 0.5, [0.0, -6.0, -12.0])
    sf.write(path, x, 48000, subtype="FLOAT")
    return path


def test_reanalyze_rebuilds_analysis_from_stored_audio(tmp_path):
    root = tmp_path / "lib"
    entry = tones.add(root, "A", "B", "lead", _analysis_dir(tmp_path), "stem",
                      reference=_note_wav(tmp_path / "stem.wav"), track=_note_wav(tmp_path / "mix.wav"))
    tones.reanalyze(entry)

    fp = json.loads((entry / "lead" / "fingerprint.json").read_text())
    assert fp["schema_version"] >= 4
    assert fp["source"]["path"] == "reference.wav"
    assert [n["midi"] for n in fp["notes"]] == [45, 57]
    harm = json.loads((entry / "lead" / "harmonics.json").read_text())
    assert [n["midi"] for n in harm["notes"]] == [45, 57]
    assert (entry / "lead" / "reference.wav").is_file()
    assert json.loads((entry / "tone.json").read_text())["roles"]["lead"]["reference"]["kind"] == "stem"


def test_reanalyze_skips_role_without_stored_audio(tmp_path):
    entry = tones.add(tmp_path / "lib", "A", "B", "lead", _analysis_dir(tmp_path), "stem")
    assert tones.reanalyze(entry) == []
