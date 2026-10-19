"""Per-clip picture repairs that have to happen before Resolve sees the footage.

Two clips need work, for unrelated reasons.

The menu scene was shot on a phone resting on a laptop, so the laptop's keyboard and
touchpad - and the ceiling light reflecting off them - sit across the bottom of frame.
Measured at y=985 and stable for the whole take.

The cold open was recorded with the phone's sharpening turned up hard: at 1:1 there are
bright halos on every leaf edge and the skin texture is crunched. That is baked into the
pixels, not a grading problem, so no amount of CDL will help it - it needs a light denoise
plus a negative unsharp to pull the halos back down.

Both are done with ffmpeg rather than inside Resolve because the result can be checked by
looking at a frame. Re-run this script after changing any parameter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CUTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SYNCED = ROOT / "Trade" / "Synced"
OUT = ROOT / "Trade" / "Prepared"

W, H = 1920, 1080

# hqdn3d: gentle spatial + stronger temporal, which is where phone noise actually lives.
# unsharp with a NEGATIVE amount softens instead of sharpening, which is what undoes an
# over-sharpened source; 0.5 is enough to kill the halo without turning the face to wax.
REPAIRS = {
    "sharpening": "hqdn3d=2:1.5:5:5,unsharp=5:5:-0.5:5:5:0.0",
}

# Applied to every footage clip, and to nothing else - a vignette over a screenshot of a
# dashboard just looks like a mistake.
#
# Vignette then grain, in that order: the grain has to sit on top or the vignette darkens it
# unevenly across the frame. Both are deliberately weak. Adding grain straight after
# denoising the cold open is not a contradiction - it is the normal colourist move of
# removing ugly sensor noise and putting back an even, filmic texture.
#
# This is baked because CDL cannot express either one, and Resolve's API has no keyframes or
# effect graph to reach for. Everything CDL *can* do stays in apply_grade.py, where it is
# still adjustable per clip on the Color page.
CINEMATIC = "vignette=angle=PI/6.5:mode=forward,noise=alls=4:allf=t"


def filters_for(cut) -> list[str]:
    chain = []
    if cut.crop_bottom:
        keep = H - cut.crop_bottom
        # Anchored at the top so Rafan's head stays where it was - centring the rescale
        # would push the top of his head out of frame, since he already sits high.
        scaled_w = int(round(W * H / keep))
        scaled_w += scaled_w % 2  # x264 needs even dimensions
        chain += [f"crop={W}:{keep}:0:0",
                  f"scale={scaled_w}:{H}:flags=lanczos",
                  f"crop={W}:{H}"]
    if cut.repair:
        if cut.repair not in REPAIRS:
            raise SystemExit(f"{cut.section}: unknown repair {cut.repair!r}")
        chain.append(REPAIRS[cut.repair])
    if cut.kind == "footage":
        chain.append(CINEMATIC)
    if chain:
        chain.append("setsar=1")
    return chain


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    for cut in CUTS:
        chain = filters_for(cut)
        if not chain or cut.src in done:
            continue
        done.add(cut.src)

        src, dst = SYNCED / f"{cut.src}.mp4", OUT / f"{cut.src}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-vf", ",".join(chain),
             "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", "-c:a", "copy", str(dst)],
            check=True,
        )
        what = []
        if cut.crop_bottom:
            what.append(f"crop {cut.crop_bottom}px, rescale x{H / (H - cut.crop_bottom):.3f}")
        if cut.repair:
            what.append(f"repair:{cut.repair}")
        if cut.kind == "footage":
            what.append("vignette+grain")
        print(f"  {cut.src:16} {' + '.join(what)}")


if __name__ == "__main__":
    main()
