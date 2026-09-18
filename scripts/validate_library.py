#!/usr/bin/env python3
"""Validate every entry of the tone library.

Per role: stored reference audio matches its sha256, fingerprint is schema >= 4
with no local path, and — when a track is stored — the track decodes to the
reference's length, the reference sits inside it at the stored offset
(cross-correlation on the reference's loudest minute), and harmonics.json has one
row per detected note. Roles with fewer than 5 detected notes are listed.

    .venv/bin/python scripts/validate_library.py [tones]
Exit 1 when any integrity check fails (few notes alone does not fail).
"""
import pathlib, sys
import numpy as np, soundfile as sf
from scipy.signal import resample_poly, fftconvolve

SR = 8000
def load(p, start=30.0, dur=60.0):
    info = sf.info(str(p)); sr = info.samplerate
    x, _ = sf.read(str(p), start=int(start*sr), frames=int(dur*sr), dtype="float32", always_2d=True)
    x = x.mean(1); g = np.gcd(SR, sr)
    return resample_poly(x, SR//g, sr//g)
def loudest_start(p, win=60.0):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True); x = x.mean(1)
    hop = int(5*sr); w = int(win*sr)
    if len(x) <= w: return 0.0
    e = [float(np.mean(x[i:i+w]**2)) for i in range(0, len(x)-w, hop)]
    return float(np.argmax(e)*5.0)
def align(stem, track):
    st = loudest_start(stem); tw = max(st - 5.0, 0.0)
    a, b = load(stem, st, 60.0), load(track, tw, 70.0)
    c = fftconvolve(b, a[::-1], mode="valid")
    k = int(np.argmax(np.abs(c)))
    seg = b[k:k+len(a)]
    r = float(np.dot(seg, a) / (np.linalg.norm(seg)*np.linalg.norm(a) + 1e-12))
    return (k/SR) - (st - tw), r

def main(root: str = "tones") -> int:
    import json
    from tone_analyzer import _common
    problems, sparse = [], []
    for m in sorted(pathlib.Path(root).glob("*/tone.json")):
        d = json.loads(m.read_text()); e = m.parent
        for role, v in sorted(d["roles"].items()):
            tag = f"{e.name}/{role}"
            ref = e / v["reference"]["file"]
            if _common.sha256_file(ref) != v["reference"]["sha256"]:
                problems.append(f"{tag}: reference sha256 mismatch")
            fp = json.loads((e / role / "fingerprint.json").read_text())
            if fp["schema_version"] < 4 or "/" in fp["source"]["path"]:
                problems.append(f"{tag}: fingerprint schema < 4 or local path")
            notes = len(fp["notes"]); rdur = fp["source"]["duration_s"]; line = "no track"
            t = v.get("track")
            if t:
                tf = e / t["file"]
                x, sr = sf.read(str(tf), dtype="float32", always_2d=True); tdur = len(x) / sr
                lag, r = align(ref, tf); off = t.get("offset_s", 0.0)
                hp = e / role / "harmonics.json"
                hn = len(json.loads(hp.read_text())["notes"]) if hp.exists() else 0
                line = f"track lag={lag * 1000:+.1f} ms (stored {off * 1000:+.1f}) r={r:.2f} harmonics={hn}"
                if abs(tdur - rdur) > 1.0:
                    problems.append(f"{tag}: track decodes to {tdur:.1f} s, reference {rdur:.1f} s")
                if abs(lag - off) > 0.005:
                    problems.append(f"{tag}: measured lag {lag * 1000:+.1f} ms, stored offset {off * 1000:+.1f} ms")
                if hn != notes:
                    problems.append(f"{tag}: {hn} harmonics rows for {notes} notes")
            if notes < 5:
                sparse.append(f"{tag}: {notes} notes detected")
            print(f"{tag:55} notes={notes:3}  {line}", flush=True)
    print("\nfew notes:\n" + ("\n".join(sparse) or "none"))
    print("\nproblems:\n" + ("\n".join(problems) or "none"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
