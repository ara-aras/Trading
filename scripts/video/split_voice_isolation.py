"""Split the cold open's audio so Voice Isolation can skip the words it would eat.

The problem it solves: Resolve's AI Voice Isolation is a single amount for a whole clip.
Set high enough to clear the birds out of the outdoor take, it also gates out "…make the AI
trade." - because that word trails off at the end of the sentence and sits at -17 to -28 dB,
which the isolator cannot tell apart from background. Set low enough to keep the word, the
birds come back. One global number cannot win.

It does not have to be global. Measuring the take shows the loud chirps land at 18.7s and
20.6-21.0s, either side of the word, while during "trade" itself the 3-8 kHz band is down at
-41 to -56 dB - the birds are nearly absent exactly where the word is. So the audio is split
into three items and isolation is only applied where it helps.

The audio is unlinked from the picture to do this, which is safe: nothing here retimes
anything, the three pieces are butt-joined at their original positions, and the video item
is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS, plan, source_path  # noqa: E402
from build_resolve_timeline import PROJECT, TIMELINE, bin_named  # noqa: E402
from resolve_env import connect, require_writable  # noqa: E402

CLIP = "PrateekIntro"
ISOLATION = 58          # what Rafan settled on for the rest of the take

# Source-time window to leave alone, in seconds. "trade." runs 19.64-20.06; padded either
# side so the isolator does not clip its attack or its tail.
PROTECT = (19.45, 20.25)


def main() -> None:
    resolve = connect()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project or project.GetName() != PROJECT:
        project = pm.LoadProject(PROJECT)
    timeline = next((project.GetTimelineByIndex(i + 1)
                     for i in range(project.GetTimelineCount())
                     if project.GetTimelineByIndex(i + 1).GetName() == TIMELINE), None)
    if timeline is None:
        raise SystemExit(f"timeline {TIMELINE!r} not found")
    project.SetCurrentTimeline(timeline)
    require_writable(timeline)

    entry = next((e for e in plan() if e.kind == "footage" and e.src == CLIP), None)
    if entry is None:
        raise SystemExit(f"{CLIP} is not in the plan")

    origin = timeline.GetStartFrame()
    lo, hi = PROTECT
    if not (entry.start < lo < hi < entry.end):
        raise SystemExit(
            f"protected window {PROTECT} is outside the cut "
            f"({entry.start:.2f}-{entry.end:.2f})")

    # Boundaries in FRAMES, not seconds. Rounding each span's ends independently lost a
    # frame across the three pieces and left a 33 ms hole before the transition, which is
    # audible as a click. Sharing the interior boundaries makes the pieces butt-join and the
    # total match the original exactly.
    f0, f3 = entry.start_frame, entry.end_frame
    f1 = int(round(lo * FPS))
    f2 = int(round(hi * FPS))
    spans = [(f0, f1, ISOLATION), (f1, f2, 0), (f2, f3, ISOLATION)]
    assert (f3 - f0) == sum(b - a for a, b, _ in spans), "spans must tile the cut exactly"

    mp = project.GetMediaPool()
    item = next((c for c in (bin_named(mp, mp.GetRootFolder(), "Footage").GetClipList() or [])
                 if c.GetName() == source_path(entry).name), None)
    if item is None:
        raise SystemExit(f"{source_path(entry).name} not in the Footage bin")

    # Clear whatever audio is currently sitting under this shot.
    a1 = timeline.GetItemListInTrack("audio", 1) or []
    old = [i for i in a1 if i.GetName() == source_path(entry).name]
    if old:
        timeline.DeleteClips(old)
        print(f"  removed {len(old)} existing audio item(s) for {CLIP}")

    placed = []
    for a, b, amount in spans:
        rec = origin + int(round(entry.tl_start * FPS)) + (a - f0)
        ok = mp.AppendToTimeline([{
            "mediaPoolItem": item,
            "startFrame": a,
            "endFrame": b,
            "trackIndex": 1,
            "recordFrame": rec,
            "mediaType": 2,
        }])
        if not ok:
            raise SystemExit(f"failed to place source frames {a}-{b}")
        placed.append((a, b, amount, rec))

    # Match by nearest start rather than exact equality - Resolve can land a placement a
    # frame off what was asked for, and an exact-key lookup then silently skips the piece.
    live = sorted(timeline.GetItemListInTrack("audio", 1) or [], key=lambda i: i.GetStart())
    for a, b, amount, rec in placed:
        it = min(live, key=lambda i: abs(i.GetStart() - rec))
        if abs(it.GetStart() - rec) > 2:
            print(f"  frames {a}-{b}: no item near {rec}")
            continue
        it.SetVoiceIsolationState({"isEnabled": amount > 0, "amount": amount})
        print(f"  src {a/FPS:6.2f}-{b/FPS:6.2f}s  @{it.GetStart()}  "
              f"dur={it.GetDuration():3d}  isolation={it.GetVoiceIsolationState()}")

    pm.SaveProject()
    print("\nsplit applied and saved")


if __name__ == "__main__":
    main()
