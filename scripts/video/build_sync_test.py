"""Render a short A/B so a human can confirm the sync correction by ear.

The offsets in edl.CONFIRMED_SHIFT come from correlating mouth movement against audio energy.
That is a proxy and it is not equally confident on every clip - the whip-pan shot reads as
+533 ms because the camera is moving, not the mouth. So the numbers get checked by someone
who can actually hear them.

For each clip this renders the same few seconds three times: the applied offset, and that
offset 200 ms either side, each labelled. Whichever reads as in sync is the right one; if
it is one of the neighbours, move that clip's entry in CONFIRMED_SHIFT by that much.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS, audio_shift  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Trade" / "ProperFootage"
OUT = ROOT / "Trade" / "Outputs"

STEP = 0.200      # how far either side to offer
SEG = 5.0         # seconds per variant
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"

# A stretch of clear, continuous dialogue in each clip - lip sync is only judgeable where
# someone is actually talking.
SAMPLES = {
    "PrateekIntro":    17.0,
    "RafanIntro":       5.0,
    "PoisonedMarket":   9.5,
    "PoisonedMarket2":  2.5,
    "Waiter":           1.5,
    "KillSwitch":       5.5,
}


def variant(stem: str, at: float, shift: float, label: str, dst: Path) -> None:
    """One labelled segment with `shift` applied to the audio."""
    if shift > 0.001:
        ms = int(round(shift * 1000))
        af = f"adelay={ms}|{ms}"
    elif shift < -0.001:
        af = f"atrim=start={abs(shift):.3f},asetpts=PTS-STARTPTS"
    else:
        af = "anull"
    af += ",loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"

    text = label.replace(":", r"\:").replace(",", r"\,")
    vf = (
        f"fps={FPS},scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"drawtext=fontfile='{FONT}':text='{text}':x=(w-tw)/2:y=h-72:"
        f"fontsize=34:fontcolor=white:box=1:boxcolor=black@0.75:boxborderw=14"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{at:.2f}", "-t", f"{SEG:.2f}", "-i", str(SRC / f"{stem}.mp4"),
         "-vf", vf, "-af", af,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
         str(dst)],
        check=True,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_synctest"
    tmp.mkdir(exist_ok=True)

    parts: list[Path] = []
    for stem, at in SAMPLES.items():
        base = audio_shift(stem)
        for tag, delta in (("A  earlier", -STEP), ("B  applied", 0.0), ("C  later", +STEP)):
            shift = base + delta
            label = (f"{stem}   {tag}   ({shift * 1000:+.0f} ms"
                     f"{'  <- current' if delta == 0 else ''})")
            dst = tmp / f"{stem}_{tag[0]}.mp4"
            variant(stem, at, shift, label, dst)
            parts.append(dst)
        print(f"  {stem:18} base {base * 1000:+.0f} ms  ->  3 variants")

    listing = tmp / "list.txt"
    listing.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8"
    )
    out = OUT / "sync-test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(out)],
        check=True,
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"\n{out}  ({float(dur):.0f}s, {len(parts)} variants)")


if __name__ == "__main__":
    main()
