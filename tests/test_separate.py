"""`separate` wraps the demucs CLI and always hands back 48 kHz stems."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from tone_analyzer import separate

FAKE_DEMUCS = r'''#!{python}
import sys, pathlib
import numpy as np, soundfile as sf
args = sys.argv[1:]
if {fail}:
    print("boom: model exploded", file=sys.stderr); sys.exit(7)
out = pathlib.Path(args[args.index("-o") + 1]); model = args[args.index("-n") + 1]
assert "--two-stems" in args and args[args.index("--two-stems") + 1] == "guitar"
track = pathlib.Path(args[-1])
d = out / model / track.stem
d.mkdir(parents=True)
t = np.arange(44100) / 44100.0
tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype("float32")
sf.write(d / "guitar.wav", np.stack([tone, tone], 1), 44100)
sf.write(d / "no_guitar.wav", np.stack([tone, tone], 1) * 0.1, 44100)
'''


def _install_fake(tmp_path: Path, monkeypatch, fail: bool = False) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "demucs"
    exe.write_text(FAKE_DEMUCS.format(python=sys.executable, fail=fail))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin:/bin")


def _track(tmp_path: Path) -> Path:
    p = tmp_path / "song.wav"
    sf.write(p, np.zeros((44100, 2), dtype="float32"), 44100)
    return p


def test_separate_writes_48k_guitar_and_rest(tmp_path, monkeypatch):
    _install_fake(tmp_path, monkeypatch)
    out = tmp_path / "out"
    assert separate.main([str(_track(tmp_path)), "--out-dir", str(out)]) == 0
    for name in ("guitar.wav", "no_guitar.wav"):
        info = sf.info(str(out / name))
        assert info.samplerate == 48000
        assert abs(info.frames / info.samplerate - 1.0) < 0.001


def test_separate_keeps_pitch(tmp_path, monkeypatch):
    _install_fake(tmp_path, monkeypatch)
    out = tmp_path / "out"
    separate.main([str(_track(tmp_path)), "--out-dir", str(out)])
    x, sr = sf.read(str(out / "guitar.wav"))
    mono = x.mean(axis=1)
    spec = np.abs(np.fft.rfft(mono))
    peak_hz = np.argmax(spec) * sr / len(mono)
    assert abs(peak_hz - 440.0) < 2.0


def test_separate_without_demucs_exits_3_with_install_hint(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "nobin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert separate.main([str(_track(tmp_path)), "--out-dir", str(tmp_path / "out")]) == 3
    err = capsys.readouterr().err
    assert "pipx install --python python3.12 demucs" in err
    assert "brew install pipx" in err  # pipx itself is often missing
    assert not (tmp_path / "out" / "guitar.wav").exists()


def test_separate_demucs_failure_exits_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _install_fake(tmp_path, monkeypatch, fail=True)
    out = tmp_path / "out"
    assert separate.main([str(_track(tmp_path)), "--out-dir", str(out)]) == 1
    assert "model exploded" in capsys.readouterr().err
    assert not (out / "guitar.wav").exists()
