"""The `tone-analyzer` console script dispatches to each module's main()."""

from __future__ import annotations

from pathlib import Path

from tone_analyzer import cli


def test_no_args_prints_usage_and_exits_2(capsys):
    rc = cli.main([])
    assert rc == 2
    assert "analyze" in capsys.readouterr().err


def test_help_exits_0(capsys):
    rc = cli.main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    for cmd in ("analyze", "compare", "eq-match", "correction-ir"):
        assert cmd in out


def test_unknown_command_exits_2(capsys):
    rc = cli.main(["frobnicate"])
    assert rc == 2
    assert "frobnicate" in capsys.readouterr().err


def test_analyze_dispatch_writes_fingerprint(clean_di_path: Path, tmp_path: Path):
    out = tmp_path / "out"
    rc = cli.main(["analyze", str(clean_di_path), "--out-dir", str(out)])
    assert rc == 0
    assert (out / "fingerprint.json").is_file()


def test_compare_and_eq_match_warn_obsolete(clean_di_path: Path, tmp_path: Path, capsys):
    cli.main(["compare", str(clean_di_path), str(clean_di_path), "--out-dir", str(tmp_path / "c")])
    assert "obsolete" in capsys.readouterr().err
    cli.main(["eq-match", str(clean_di_path), str(clean_di_path), "--gains", "0,0,0,0,0,0,0,0"])
    assert "obsolete" in capsys.readouterr().err


def test_help_lists_harmonics_and_marks_obsolete(capsys):
    cli.main(["--help"])
    out = capsys.readouterr().out
    assert "harmonics" in out
    assert "obsolete" in out


def test_correction_ir_warns_obsolete(clean_di_path: Path, tmp_path: Path, capsys):
    cli.main(["correction-ir", str(clean_di_path), str(clean_di_path), "--output", str(tmp_path / "ir.wav")])
    assert "obsolete" in capsys.readouterr().err


def test_help_lists_tones_and_separate(capsys):
    cli.main(["--help"])
    out = capsys.readouterr().out
    assert "tones" in out and "separate" in out


def test_tones_dispatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TONE_ANALYZER_TONES_PATH", str(tmp_path / "lib"))
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert cli.main(["tones", "find", "nothing"]) == 1
