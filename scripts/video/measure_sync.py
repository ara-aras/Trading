"""Measure the real audio/video offset in each clip, by correlating mouth motion to sound.

The earlier sync check compared the render against its own source, which proves the edit
did not introduce drift and says nothing about whether the source was in sync to begin
with. It never was: these were recorded with a Bluetooth headset as the microphone, and
that link has latency the camera does not compensate for, so the audio sits late against
the picture by a fixed amount.

This measures it without needing to hear anything. Two signals per clip, both at frame rate:

  picture  mean absolute difference between consecutive frames, inside a box around the
           speaker's mouth. Talking moves those pixels; nothing else in a locked-off
           interview shot does, much.
  sound    short-term RMS of the audio.

Speech makes both rise and fall together, so the lag that maximises their cross-correlation
is the offset between them. Positive result = audio is LATE and must be pulled earlier.

It is a proxy, not a clapperboard. Treat a result under about 2 frames as "no reading", and
sanity-check a large one against the render before trusting it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SEARCH_S = 0.75          # how far either way to look
MIN_CONFIDENT = 2.0      # frames; below this the reading is noise


def picture_motion(path: Path, start: float, dur: float, box: str) -> np.ndarray:
    """Per-frame motion energy inside `box` (an ffmpeg crop expression)."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(path),
         "-vf", f"fps={FPS},crop={box},scale=64:64,format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    frames = np.frombuffer(out, dtype=np.uint8).astype(np.float32)
    n = frames.size // (64 * 64)
    frames = frames[: n * 64 * 64].reshape(n, 64 * 64)
    return np.abs(np.diff(frames, axis=0)).mean(axis=1)


def sound_energy(path: Path, start: float, dur: float) -> np.ndarray:
    """Per-frame RMS of the audio, on the same grid as picture_motion."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(path),
         "-vn", "-ac", "1", "-ar", str(FPS * 400), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    a = np.frombuffer(out, dtype=np.float32)
    n = a.size // 400
    return np.sqrt((a[: n * 400].reshape(n, 400) ** 2).mean(axis=1))


def lag_frames(pic: np.ndarray, snd: np.ndarray) -> tuple[float, float]:
    """Best lag in frames, and a 0-1 confidence from the peak's prominence."""
    n = min(pic.size, snd.size)
    if n < FPS * 3:
        return 0.0, 0.0
    a = pic[:n] - pic[:n].mean()
    b = snd[:n] - snd[:n].mean()
    if not a.any() or not b.any():
        return 0.0, 0.0
    a /= np.linalg.norm(a)
    b /= np.linalg.norm(b)

    span = int(SEARCH_S * FPS)
    lags = np.arange(-span, span + 1)
    # a[l+k] pairs with b[k], so a positive lag means picture happens later than sound - the
    # sound is EARLY. A negative lag is the Bluetooth case: sound arrives LATE.
    corr = np.array([np.dot(a[max(0, l):n + min(0, l)], b[max(0, -l):n - max(0, l)])
                     for l in lags])
    best = int(np.argmax(corr))
    peak = corr[best]
    # Prominence against everything outside a small window round the peak.
    mask = np.abs(lags - lags[best]) > FPS * 0.15
    floor = corr[mask].max() if mask.any() else 0.0
    conf = float(max(0.0, (peak - floor) / peak)) if peak > 0 else 0.0
    return float(lags[best]), conf


# Mouth boxes, as ffmpeg crop expressions. Framing differs per clip, so these are set by
# where the speaker actually is rather than assuming centre.
# Framing differs per clip and a box that misses the mouth reads as noise, so several
# candidates are tried per clip and the most confident one wins.
BOXES = [
    "iw*0.30:ih*0.26:iw*0.36:ih*0.14",
    "iw*0.30:ih*0.26:iw*0.36:ih*0.22",
    "iw*0.30:ih*0.26:iw*0.36:ih*0.30",
    "iw*0.40:ih*0.34:iw*0.30:ih*0.16",
    "iw*0.50:ih*0.40:iw*0.25:ih*0.12",
]

CLIPS = [
    # (stem, start, dur)
    ("PrateekIntro",    16.0, 21.0),
    ("RafanIntro",       4.0, 26.0),
    ("PoisonedMarket",   2.0, 11.0),
    ("PoisonedMarket2",  2.0, 15.0),
    ("Waiter",           1.0, 27.0),
    ("KillSwitch",       5.0, 10.0),
]


def main() -> None:
    src_dir = ROOT / "Trade" / "ProperFootage"
    print(f"{'clip':18} {'lag (frames)':>13} {'lag (ms)':>10} {'confidence':>11}")
    print("-" * 56)
    readings = []
    for stem, start, dur in CLIPS:
        p = src_dir / f"{stem}.mp4"
        if not p.exists():
            print(f"{stem:18}  missing")
            continue
        snd = sound_energy(p, start, dur)
        lag, conf = 0.0, -1.0
        for box in BOXES:
            l, c = lag_frames(picture_motion(p, start, dur, box), snd)
            if c > conf:
                lag, conf = l, c
        ms = lag / FPS * 1000
        mark = "" if abs(lag) >= MIN_CONFIDENT and conf > 0.12 else "   (weak)"
        if not mark:
            readings.append(lag)
        print(f"{stem:18} {lag:13.1f} {ms:10.0f} {conf:11.2f}{mark}")

    if readings:
        med = float(np.median(readings))
        print("-" * 56)
        print(f"median of {len(readings)} confident reading(s): "
              f"{med:.1f} frames = {med / FPS * 1000:.0f} ms")
        print("positive => audio is LATE; pull it earlier by that much")


if __name__ == "__main__":
    main()
