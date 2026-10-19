"""A conservative shot-matching grade, applied as ASC CDL on each timeline item.

Two measured problems, and only those two:

  Luminance. The bottle sketch cuts from PoisonedMarket (Y 112) straight into
  PoisonedMarket2 (Y 148) - a 36-point jump between adjacent shots of the same scene,
  which reads as a mistake. Every footage clip is pulled toward a common target.

  Saturation. The footage is flat, 5 to 12 on signalstats' scale, so everything gets a
  modest lift.

On top of that it applies a gentle filmic split - warm highlights, cool shadows - and runs
Studio's stabiliser on the two handheld clips.

Deliberately NOT corrected: the overall warm cast. Cr sits above neutral on all six clips by a
similar amount, so it is the phone's white balance rather than a mismatch between shots,
and pulling red out of it is the fastest way to make everyone look ill.

Corrections are applied at STRENGTH, not in full. Matching two shots exactly tends to
flatten whichever one was better lit; most of the way there is enough for the cut to stop
drawing attention to itself. All of it is CDL on the item, so it can be dialled back or
cleared per clip on the Color page.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import plan, source_path  # noqa: E402
from build_resolve_timeline import TIMELINE  # noqa: E402
from resolve_env import connect, require_writable  # noqa: E402

# The match target is the MEDIAN of the clips themselves, computed at run time, not a fixed
# number. Shot matching is about the shots agreeing with each other; an absolute target just
# means every clip gets dragged the same direction and the one that was correctly exposed
# gets dragged too. A fixed 125 also broke the moment prep_footage started centre-cropping
# the measurement, because the reference changed under it.
STRENGTH = 0.70       # fraction of the way to the median
SATURATION = 1.12
POWER_CLAMP = (0.80, 1.25)   # keep gamma moves gentle enough to stay natural

# A filmic split: warm highlights, cool shadows. CDL is out = (in * slope + offset) ** power,
# so slope tilts the brighter end and offset tilts the darker end, which is exactly the
# separation a film print gives you.
#
# Values are small on purpose. The footage already carries a warm cast from the phone's white
# balance, so pushing red much further turns skin orange; the cool lift in the shadows is
# doing most of the work here, and it partly counterweights that existing cast.
FILM_SLOPE = (1.012, 1.000, 0.990)     # R, G, B
FILM_OFFSET = (-0.002, 0.000, 0.010)

# Handheld. Measured by frame-to-frame motion: these two run 3.8-5.8 against 1.6-1.9 for the
# locked-off lab shots. PoisonedMarket2 measures highest of all at 10.6, but that is the
# whip pan up off the floor - stabilising it would fight the shot, so it is not in this set.
STABILIZE = {"PrateekIntro", "RafanIntro"}

# Stabilisation is the heaviest thing this script does - it runs Studio's Neural Engine
# analysis per clip, and Resolve has died partway through it. Set BRIGHTLINE_NO_STABILIZE=1
# to apply the CDL only, which has never been the step that fell over.
SKIP_STABILIZE = os.environ.get("BRIGHTLINE_NO_STABILIZE") == "1"


def measure_y(path: Path, start: float) -> float:
    """Mean luma of the CENTRE of frame, over a few seconds of the part actually used.

    Centre-cropped on purpose. prep_footage bakes a vignette, so a whole-frame mean is
    dragged down by the darkened corners - matching on that number makes the grade brighten
    the shot to compensate and washes the vignette straight back out. The subject is in the
    middle, and the middle is what should match between shots.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start + 1:.2f}", "-t", "4", "-i", str(path),
         "-vf", "crop=iw*0.55:ih*0.55,signalstats,metadata=print:file=-", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    vals = [float(m) for m in
            re.findall(r"lavfi\.signalstats\.YAVG=([\d.\-]+)", r.stdout)]
    if not vals:
        raise RuntimeError(f"no luma stats for {path.name}")
    return sum(vals) / len(vals)


def power_for(y: float, target: float) -> float:
    """CDL power that moves mean luma toward the target: out = in ** power."""
    src = max(1e-3, min(0.999, y / 255.0))
    want = src + (target / 255.0 - src) * STRENGTH
    want = max(1e-3, min(0.999, want))
    p = math.log(want) / math.log(src)
    return max(POWER_CLAMP[0], min(POWER_CLAMP[1], p))


def main() -> None:
    resolve = connect()
    project = resolve.GetProjectManager().GetCurrentProject()

    timeline = None
    for i in range(project.GetTimelineCount()):
        tl = project.GetTimelineByIndex(i + 1)
        if tl and tl.GetName() == TIMELINE:
            timeline = tl
            break
    if timeline is None:
        raise SystemExit(f"timeline {TIMELINE!r} not found - run build_resolve_timeline first")
    project.SetCurrentTimeline(timeline)

    require_writable(timeline)

    entries = plan()
    items = timeline.GetItemListInTrack("video", 1) or []
    if len(items) != len(entries):
        raise SystemExit(f"V1 has {len(items)} items, expected {len(entries)}")

    # Measure everything first - the target depends on the whole set.
    cache: dict[str, float] = {}
    for cut in entries:
        if cut.kind == "footage" and cut.src not in cache:
            cache[cut.src] = measure_y(source_path(cut), cut.start)
    ys = sorted(cache.values())
    target = ys[len(ys) // 2] if len(ys) % 2 else (ys[len(ys) // 2 - 1] + ys[len(ys) // 2]) / 2
    print(f"match target (median of {len(ys)} clips): {target:.1f}")
    print()

    print(f"{'section':22} {'Y':>6} {'power':>6} {'sat':>5}")
    print("-" * 44)
    for cut, item in zip(entries, items):
        if cut.kind != "footage":
            # Screen inserts are already rendered at the level they should be (grading a
            # screenshot of a dashboard only makes the text less crisp), and a transition
            # clip is baked from two already-graded neighbours.
            continue
        y = cache[cut.src]
        p = power_for(y, target)
        ok = item.SetCDL({
            "NodeIndex": "1",
            "Slope": " ".join(f"{v:.4f}" for v in FILM_SLOPE),
            "Offset": " ".join(f"{v:.4f}" for v in FILM_OFFSET),
            "Power": f"{p:.4f} {p:.4f} {p:.4f}",
            "Saturation": f"{SATURATION:.3f}",
        })

        stab = ""
        if cut.src in STABILIZE and SKIP_STABILIZE:
            stab = "  (stabilize skipped)"
        elif cut.src in STABILIZE:
            # Studio's Neural Engine stabiliser, run per item. It analyses on the spot, so
            # this is the slow part of the pass.
            stab = "  stabilized" if item.Stabilize() else "  STABILIZE FAILED"

        print(f"{cut.name:22} {y:6.1f} {p:6.3f} {SATURATION:5.2f}"
              f"{'' if ok else '   <-- CDL FAILED'}{stab}", flush=True)
        # Save as we go. A crash three clips in used to lose the whole pass.
        resolve.GetProjectManager().SaveProject()

    resolve.GetProjectManager().SaveProject()
    print("\ngrade applied and saved")


if __name__ == "__main__":
    main()
