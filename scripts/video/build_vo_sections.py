"""Fit each screen insert to the exact duration its section needs.

The inserts were recorded at whatever length the animation took; the cut list wants
specific lengths, sized to the script's word counts at 150 wpm so Rafan has room to dub
over them. Retiming with setpts rather than freezing a final frame keeps the scroll moving
for the whole shot - an 18-second hold on a frozen screenshot looks like a playback fault.

Output frame counts are exact, so Resolve never has to resample and the timeline maths in
build_resolve_timeline.py stays whole-frame.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CUTS, FPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "Trade" / "Captures"
OUT = ROOT / "Trade" / "VOSections"


def probe(p: Path) -> float:
    return float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for cut in CUTS:
        # Only the screen inserts are retimed here. Chapters and bloopers are their own
        # media with their own lengths, and iterating "anything not footage" swept them in.
        if cut.kind not in ("vo", "insert"):
            continue
        src = CAPTURES / f"{cut.src}.mp4"
        if not src.exists():
            print(f"  {cut.src:20} MISSING {src}")
            continue

        have, want = probe(src), cut.duration
        factor = want / have
        frames = int(round(want * FPS))
        dst = OUT / f"{cut.src}.mp4"

        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", str(src),
                "-vf", f"setpts={factor:.6f}*PTS,fps={FPS}",
                # -frames caps it exactly; retiming can leave a frame either side.
                "-frames:v", str(frames),
                "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-pix_fmt", "yuv420p", "-an", str(dst),
            ],
            check=True,
        )
        got = probe(dst)
        flag = "" if abs(got - want) < 0.05 else "  <-- off"
        print(f"  {cut.src:20} {have:5.1f}s -> {got:5.1f}s  (x{1/factor:4.2f}){flag}")


if __name__ == "__main__":
    main()
