"""Place the ducked music bed on its own audio track, without rebuilding the timeline.

build_resolve_timeline.py recreates the timeline from scratch, which throws away the grade
and means a full re-grade afterwards. The music is the last thing added and depends on a
render that only exists once everything else is done, so doing it that way would mean
grading twice and rendering twice on a machine that has already crashed Resolve five times.

This just imports the bed and drops it on A4 of the timeline that is already there.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS  # noqa: E402
from build_resolve_timeline import MUSIC, MUSIC_TRACK, PROJECT, TIMELINE, bin_named  # noqa: E402
from resolve_env import connect  # noqa: E402


def main() -> None:
    if not MUSIC.exists():
        raise SystemExit(f"no music bed at {MUSIC} - run build_music.py first")

    resolve = connect()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project or project.GetName() != PROJECT:
        project = pm.LoadProject(PROJECT)
    if not project:
        raise SystemExit(f"could not open project {PROJECT!r}")

    timeline = next((project.GetTimelineByIndex(i + 1)
                     for i in range(project.GetTimelineCount())
                     if project.GetTimelineByIndex(i + 1).GetName() == TIMELINE), None)
    if timeline is None:
        raise SystemExit(f"timeline {TIMELINE!r} not found")
    project.SetCurrentTimeline(timeline)

    mp = project.GetMediaPool()
    folder = bin_named(mp, mp.GetRootFolder(), "Music")
    mp.SetCurrentFolder(folder)

    # Clear any previous bed so re-running cannot stack two copies on the track.
    for clip in (folder.GetClipList() or []):
        mp.DeleteClips([clip])
    for existing in (timeline.GetItemListInTrack("audio", MUSIC_TRACK) or []):
        timeline.DeleteClips([existing])

    imported = mp.ImportMedia([str(MUSIC)]) or []
    item = imported[0] if imported else next(
        (c for c in (folder.GetClipList() or []) if c.GetName() == MUSIC.name), None)
    if item is None:
        raise SystemExit("music did not import")

    while timeline.GetTrackCount("audio") < MUSIC_TRACK:
        timeline.AddTrack("audio")

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(MUSIC)],
        capture_output=True, text=True, check=True).stdout.strip())
    origin = timeline.GetStartFrame()
    frames = max(1, int(round(dur * FPS)))

    # Never let the bed outlast the picture. A music file longer than the cut extends the
    # timeline, and the render then spends its last stretch on music over nothing - which is
    # exactly what happened when the bed was built from a stale, longer reference render.
    v1 = timeline.GetItemListInTrack("video", 1) or []
    picture = sum(i.GetDuration() for i in v1)
    if frames > picture:
        print(f"  trimming bed {frames} -> {picture} frames to match the picture")
        frames = picture

    ok = mp.AppendToTimeline([{
        "mediaPoolItem": item,
        "startFrame": 0,
        "endFrame": frames,
        "trackIndex": MUSIC_TRACK,
        "recordFrame": origin,
        "mediaType": 2,
    }])
    timeline.SetTrackName("audio", MUSIC_TRACK, "music")

    placed = timeline.GetItemListInTrack("audio", MUSIC_TRACK) or []
    print(f"  A{MUSIC_TRACK} music: {frames} frames ({dur:.1f}s) @ {origin} "
          f"-> {len(placed)} item(s)  {'ok' if ok else 'FAILED'}")
    pm.SaveProject()


if __name__ == "__main__":
    main()
