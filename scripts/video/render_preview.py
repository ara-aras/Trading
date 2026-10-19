"""Render a watchable preview of the rough cut, in segments.

This is a preview, not the deliverable. The deliverable is the timeline in Resolve, which
stays exactly as it is - every cut still its own trimmable item. This just produces
something to scrub on a phone and decide what to re-cut.

Segmented, because rendering the whole thing in one job kept taking Resolve down. The cut
now runs 6:15 over 53 timeline items, with two Neural Engine stabilised clips, CDL on every
piece of footage, and three alpha overlay tracks (RLE plus a 269 MB ProRes 4444) composited
on top - on a 16 GB machine with about 6 GB free. Peak memory, not total work, is what
kills it.

Rendering ~75 seconds at a time keeps the peak far lower, and a crash costs one segment
instead of the entire job. The segments are concatenated with ffmpeg's stream copy, so
there is no quality loss at the joins and no re-encode.

If Resolve dies anyway, re-running skips the segments that already exist.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS  # noqa: E402
from build_resolve_timeline import TIMELINE  # noqa: E402
from resolve_env import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Trade" / "Outputs"
SEGDIR = OUT / "_segments"
NAME = "brightline-rough-cut"

SEGMENT_SECONDS = 75.0


def stale_segments(start: int, end: int) -> bool:
    """True when the cached segments belong to a different cut.

    Without this the resume logic happily reuses segments from an older edit: a locked file
    made one `rm -rf` fail, and the next run rebuilt a 6:15 render for a 5:50 timeline and
    reported success. The stamp records which timeline range the cache was built from.
    """
    stamp = SEGDIR / "timeline.stamp"
    want = f"{start}-{end}"
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == want:
        return False
    for f in SEGDIR.glob("seg*.mp4"):
        try:
            f.unlink()
        except OSError as exc:
            raise SystemExit(
                f"cannot clear the stale segment cache ({f.name}: {exc}). "
                f"Something still has it open - close it and re-run."
            )
    SEGDIR.mkdir(parents=True, exist_ok=True)
    stamp.write_text(want, encoding="utf-8")
    return True


def find_timeline(project):
    for i in range(project.GetTimelineCount()):
        tl = project.GetTimelineByIndex(i + 1)
        if tl and tl.GetName() == TIMELINE:
            return tl
    raise SystemExit(f"timeline {TIMELINE!r} not found")


def render_segment(resolve, project, timeline, index: int,
                   mark_in: int, mark_out: int) -> Path:
    """One segment, by timeline frame range. Returns the file it produced."""
    dst = SEGDIR / f"seg{index:02d}.mp4"
    if dst.exists() and dst.stat().st_size > 1_000_000:
        print(f"  seg{index:02d}  already rendered, skipping")
        return dst

    project.DeleteAllRenderJobs()
    # Load a stock preset FIRST. Render settings persist on the project, so a one-off job
    # that set ExportVideo=False left every later render audio-only - a 14 MB "finished
    # film" with no video stream that still reported success. The preset resets the lot.
    if not project.LoadRenderPreset("H.264 Master"):
        print("  warning: could not load the H.264 Master preset")
    if not project.SetCurrentRenderFormatAndCodec("mp4", "H264"):
        raise SystemExit("could not select mp4/H264")
    project.SetRenderSettings({
        "TargetDir": str(SEGDIR),
        "CustomName": dst.stem,
        # MarkIn/MarkOut are ABSOLUTE timeline frames - the same convention as recordFrame,
        # so they start at the timeline origin (108000 at 30fps), not at zero. Passing
        # 0-based numbers renders a fraction of a second and still reports success.
        # SelectAllFrames must also be off or they are ignored entirely.
        "SelectAllFrames": False,
        "MarkIn": mark_in,
        "MarkOut": mark_out,
        "FormatWidth": 1920,
        "FormatHeight": 1080,
        "VideoQuality": 0,
        "AudioCodec": "aac",
        "AudioBitDepth": 16,
        "ExportVideo": True,
        "ExportAudio": True,
    })

    job = project.AddRenderJob()
    if not job:
        raise SystemExit(f"seg{index:02d}: AddRenderJob failed")
    project.StartRendering(job)

    last = -1
    while True:
        try:
            if not project.IsRenderingInProgress():
                break
            st = project.GetRenderJobStatus(job) or {}
            pct = st.get("CompletionPercentage", 0)
        except Exception:
            # The handle goes stale if Resolve restarts under us. Treat that as a failed
            # segment rather than letting a TypeError surface as "render complete".
            raise RuntimeError(f"seg{index:02d}: lost the connection to Resolve mid-render")
        if pct != last:
            print(f"  seg{index:02d}  {pct:3d}%", flush=True)
            last = pct
        time.sleep(3)

    made = sorted(SEGDIR.glob(f"{dst.stem}*"), key=lambda p: p.stat().st_mtime)
    if not made:
        raise RuntimeError(f"seg{index:02d}: render reported done but produced no file")
    out = made[-1]
    if out != dst:
        out.replace(dst)

    # Resolve reports success for an audio-only render just as happily as a real one.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(dst)],
        capture_output=True, text=True).stdout.strip()
    if not probe:
        raise RuntimeError(
            f"seg{index:02d}: rendered with no video stream. Render settings on the project "
            f"are stale - ExportVideo is off."
        )
    return dst


def main() -> None:
    SEGDIR.mkdir(parents=True, exist_ok=True)
    resolve = connect()
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = find_timeline(project)
    project.SetCurrentTimeline(timeline)
    resolve.OpenPage("deliver")

    start = timeline.GetStartFrame()
    end = timeline.GetEndFrame()
    if stale_segments(start, end):
        print("  segment cache was from a different cut - cleared")
    total = end - start
    step = int(SEGMENT_SECONDS * FPS)
    bounds = [start + o for o in range(0, total, step)] + [end]
    print(f"timeline {total} frames ({total / FPS / 60:.2f} min) "
          f"-> {len(bounds) - 1} segments of <= {SEGMENT_SECONDS:.0f}s")

    parts = []
    for i in range(len(bounds) - 1):
        parts.append(render_segment(resolve, project, timeline, i,
                                    bounds[i], bounds[i + 1] - 1))

    listing = SEGDIR / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts),
                       encoding="utf-8")
    final = OUT / f"{NAME}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(final)],
        check=True,
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(final)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"\n{final}  ({final.stat().st_size / 1e6:.0f} MB, {float(dur):.1f}s)")


if __name__ == "__main__":
    main()
