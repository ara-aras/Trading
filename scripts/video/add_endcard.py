"""Place the poster end card on its own track over the tail of the close.

Separate from build_resolve_timeline on purpose. A full rebuild recreates the timeline from
scratch, which throws away everything applied to it afterwards - the CDL grade on every
clip, the Neural Engine stabilisation on the two handheld takes, and the three-way audio
split that keeps the word "trade" out of the voice isolator. This adds one item to one new
track and touches nothing else.

The card goes on V5, above the captions on V2, because it is opaque. The captions that fall
inside its six seconds are burned into the card itself by build_endcard.py; the ones on V2
are still there underneath, drawn behind the poster and therefore invisible. That is why
this is safe to run without re-rendering captions.mov.

Re-runnable: it clears whatever is already on V5 first.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS  # noqa: E402
from build_endcard import OUT as ENDCARD, SECONDS, start_time  # noqa: E402
from build_resolve_timeline import PROJECT, TIMELINE, bin_named  # noqa: E402
from resolve_env import connect, require_writable  # noqa: E402

TRACK = 5
LABEL = "end card"


def main() -> None:
    if not ENDCARD.exists():
        raise SystemExit(f"no end card at {ENDCARD} - run build_endcard.py first")

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

    while timeline.GetTrackCount("video") < TRACK:
        timeline.AddTrack("video")

    old = timeline.GetItemListInTrack("video", TRACK) or []
    if old:
        timeline.DeleteClips(old)
        print(f"  cleared {len(old)} item(s) from V{TRACK}")
        # Commit the delete before importing. Doing both in one breath is what has taken
        # Resolve down before.
        pm.SaveProject()

    mp = project.GetMediaPool()
    folder = bin_named(mp, mp.GetRootFolder(), "Overlays")
    mp.SetCurrentFolder(folder)
    # ImportMedia returns nothing for a path already in the pool, so reconcile by name
    # rather than trusting the return value.
    imported = mp.ImportMedia([str(ENDCARD)]) or []
    pool = {c.GetName(): c for c in (folder.GetClipList() or [])}
    for it in imported:
        pool.setdefault(it.GetName(), it)
    item = pool.get(ENDCARD.name)
    if item is None:
        raise SystemExit(f"{ENDCARD.name} is not in the Overlays bin after import")

    frames = int(item.GetClipProperty("Frames"))
    want = int(round(SECONDS * FPS))
    if frames != want:
        raise SystemExit(f"{ENDCARD.name} is {frames} frames, expected {want}")

    # recordFrame is ABSOLUTE - the timeline starts at 01:00:00:00, frame 108000 at 30 fps,
    # not at zero.
    origin = timeline.GetStartFrame()
    at = origin + int(round(start_time() * FPS))
    ok = mp.AppendToTimeline([{
        "mediaPoolItem": item,
        "startFrame": 0,
        "endFrame": frames,
        "trackIndex": TRACK,
        "recordFrame": at,
        "mediaType": 1,
    }])
    timeline.SetTrackName("video", TRACK, LABEL)
    if not ok:
        raise SystemExit(f"failed to place the end card at frame {at}")

    placed = timeline.GetItemListInTrack("video", TRACK) or []
    for it in placed:
        print(f"  V{TRACK}: {it.GetName()}  @{it.GetStart()}  {it.GetDuration()} frames "
              f"({start_time():.2f}s)")

    pm.SaveProject()
    print("\nend card placed and saved")


if __name__ == "__main__":
    main()
