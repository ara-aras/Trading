"""Assemble the rough cut in DaVinci Resolve as a real, trimmable timeline.

Every cut in edl.py becomes its own timeline item, so each edit point is an actual edit
point that can be rippled and slipped by hand. Nothing here flattens to a rendered file -
finishing and export stay in Resolve.

Track layout:
    V5  end card   the poster, over the tail of the close - see add_endcard.py
    V4  motion     HyperFrames motion graphics, anchored to one section
    V3  graphics   title card and the UNVERIFIED / REJECTED stamps
    V2  captions   word-by-word captions, on-camera and voiceover alike
    V1  the cut    footage, screen inserts and rendered transitions

V5 is not built here. Like apply_grade.py and split_voice_isolation.py, add_endcard.py runs
against the finished timeline, so a rebuild from this script has to be followed by those
three or the cut loses its grade, its audio split and its end card.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CUTS, FPS, plan, source_path  # noqa: E402
from vo_audio import LEAD, VO_AUDIO, vo_duration  # noqa: E402
from resolve_env import connect, require_writable  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OVERLAYS = ROOT / "Trade" / "Overlays"

PROJECT = "Brightline"
TIMELINE = "Brightline - rough cut"

OVERLAY_TRACKS = [  # (file, track index, label) - each spans the whole timeline
    ("captions.mov", 2, "captions"),
    ("graphics.mov", 3, "graphics"),
]

# HyperFrames motion graphics. Unlike the three above these are short and land on one
# section, so each is anchored by section name and trimmed to that item's length.
MOTION_DIR = ROOT / "Trade" / "Graphics" / "videos" / "brightline-overlays" / "renders"
# Full-screen graphics that TAKE OVER the picture while the dialogue underneath keeps
# playing. They sit on a track above V1 and fade their own background up and down, so no
# transition clip is needed on either side and the audio is never cut.
MOTION_OVERLAYS = [  # (file, track index, label, section, seconds into that section)
    ("cycle_editorial.mov", 4, "motion gfx", "2 one cycle", 4.5),
]

# Sound effects, all synthesised by gen_sfx.py so nothing here carries a licence.
# Anchored to a plan item by name, with an offset in seconds, on their own audio track so
# they can be muted or moved without touching the dialogue.
SFX_DIR = ROOT / "Trade" / "SFX"
SFX_TRACK = 2
VO_TRACK = 3
MUSIC_TRACK = 4
# Built by build_music.py, which ducks it against the finished mix. Optional: the timeline
# builds fine without it, which matters because the music is keyed off a render that only
# exists after the first pass.
MUSIC = ROOT / "Trade" / "Music" / "music_ducked.wav"
SFX_CUES = [  # (file, anchor plan-item name, offset seconds)
    ("whoosh.wav", "-> 9 close", -0.10),          # into the dip to black
    ("sting.wav", "b1 prateek intro", 0.05),  # under the BLOOPERS card
]


def get_or_create_project(pm):
    """Reuse the project if it exists so re-runs don't litter the database."""
    proj = pm.LoadProject(PROJECT)
    if proj is None:
        proj = pm.CreateProject(PROJECT)
    if proj is None:
        raise RuntimeError(f"could not open or create project {PROJECT!r}")
    return proj


def bin_named(mp, root, name):
    for f in root.GetSubFolderList():
        if f.GetName() == name:
            return f
    return mp.AddSubFolder(root, name)


def main() -> None:
    resolve = connect()
    print(f"connected: {resolve.GetProductName()} {resolve.GetVersionString()}")
    resolve.OpenPage("edit")

    pm = resolve.GetProjectManager()
    project = get_or_create_project(pm)

    # Frame rate has to be right before anything is imported: Resolve locks the timeline
    # rate once a timeline exists, and a mismatch shows up as a uniform duration error
    # across every clip rather than as an obvious failure.
    for key, val in (
        ("timelineFrameRate", str(FPS)),
        ("timelineResolutionWidth", "1920"),
        ("timelineResolutionHeight", "1080"),
        ("videoMonitorFormat", "HD 1080p 30"),
    ):
        project.SetSetting(key, val)
    got = project.GetSetting("timelineFrameRate")
    print(f"project: {project.GetName()}  @ {got} fps")

    mp = project.GetMediaPool()
    root = mp.GetRootFolder()

    # --- clear ----------------------------------------------------------------
    # ImportMedia happily re-imports a path the pool already holds, so every re-run used to
    # add another copy of all 40-odd clips. That reached 75 entries - 25 copies of the
    # footage bin, 28 of the transitions - several GB of duplicated ProRes and RLE alpha,
    # and Resolve fell over trying to index it. The timeline goes first: clips that are in
    # use cannot be deleted.
    for tl in [project.GetTimelineByIndex(i + 1)
               for i in range(project.GetTimelineCount())]:
        if tl and tl.GetName() == TIMELINE:
            project.SetCurrentTimeline(tl)
            mp.DeleteTimelines([tl])
            break

    pm.SaveProject()

    removed = 0
    for name in ("Footage", "Inserts", "Transitions", "Chapters",
                 "Overlays", "SFX", "VO", "Music"):
        folder = bin_named(mp, root, name)
        clips = folder.GetClipList() or []
        if clips:
            mp.DeleteClips(clips)
            removed += len(clips)
    if removed:
        print(f"  cleared {removed} clip(s) from the managed bins")
    # Save between the destructive step and the import. Deleting a few dozen large clips
    # and immediately re-importing in the same breath is what kept taking Resolve down;
    # letting it commit the deletion first has been stable.
    pm.SaveProject()

    # --- import ---------------------------------------------------------------
    items_plan = plan()
    wanted: dict[str, list[Path]] = {
        "Footage": [], "Inserts": [], "Transitions": [], "Chapters": [],
        "Overlays": [], "SFX": [], "VO": [], "Music": []}
    for entry in items_plan:
        p = source_path(entry)
        bucket = {"footage": "Footage", "blooper": "Footage",
                  "transition": "Transitions",
                  "chapter": "Chapters"}.get(entry.kind, "Inserts")
        if p not in wanted[bucket]:
            wanted[bucket].append(p)
    wanted["Overlays"] = [OVERLAYS / f for f, _, _ in OVERLAY_TRACKS]
    wanted["Overlays"] += [MOTION_DIR / f for f, _, _, _, _ in MOTION_OVERLAYS]
    wanted["SFX"] = [SFX_DIR / f for f, _, _ in SFX_CUES]
    wanted["VO"] = [ROOT / "Trade" / "VOAudio" / f"{s}.wav" for s in VO_AUDIO.values()]
    wanted["Music"] = [MUSIC] if MUSIC.exists() else []

    missing = [p for ps in wanted.values() for p in ps if not p.exists()]
    if missing:
        raise SystemExit("missing inputs:\n  " + "\n  ".join(str(m) for m in missing))

    items: dict[str, object] = {}
    for bucket, paths in wanted.items():
        folder = bin_named(mp, root, bucket)
        mp.SetCurrentFolder(folder)

        # Reconciled by name rather than trusting the return value: ImportMedia returns
        # nothing for a path the pool already holds, which would otherwise read as
        # "imported 0 of 4" even when everything needed is present.
        imported = mp.ImportMedia([str(p) for p in paths]) or []
        existing = {c.GetName(): c for c in (folder.GetClipList() or [])}
        for it in imported:
            existing.setdefault(it.GetName(), it)

        missing = [p.name for p in paths if p.name not in existing]
        if missing:
            raise RuntimeError(f"{bucket}: not in media pool after import: {missing}")
        for path in paths:
            items[path.name] = existing[path.name]
        print(f"  {len(paths):2d} in {bucket} ({len(imported)} newly imported)")
    pm.SaveProject()

    # Resolve is the authority on frame rate, not ffprobe - a variable-rate source can
    # report 29.08 and still ingest at a flat 30. Everything was conformed to CFR 30, so
    # this should agree; if it ever doesn't, the cut maths is wrong and not the clip.
    for name, it in items.items():
        fps = it.GetClipProperty("FPS")
        if abs(float(fps) - FPS) > 0.01:
            raise SystemExit(f"{name} ingested at {fps} fps, expected {FPS}")

    # --- V1: the cut ----------------------------------------------------------
    mp.SetCurrentFolder(root)
    timeline = mp.CreateEmptyTimeline(TIMELINE)
    if timeline is None:
        raise RuntimeError("could not create timeline")
    project.SetCurrentTimeline(timeline)

    clip_infos = []
    for entry in items_plan:
        item = items[source_path(entry).name]
        # Footage keeps its in/out in the source; inserts and transitions are already cut
        # to length, so they play from their own frame 0.
        if entry.kind == "footage":
            start, end = entry.start_frame, entry.end_frame
        else:
            start, end = 0, entry.frames
        clip_infos.append({
            "mediaPoolItem": item,
            "startFrame": start,
            # endFrame is EXCLUSIVE: duration is endFrame - startFrame. Passing end - 1
            # here made every one of the 15 clips exactly one frame short.
            "endFrame": end,
            "trackIndex": 1,
            # No mediaType here. mediaType 1 means video ONLY, which is what silently left
            # the whole cut mute; omitting it brings each clip's linked audio along.
        })

    appended = mp.AppendToTimeline(clip_infos)
    if not appended:
        raise RuntimeError("AppendToTimeline returned nothing")
    print(f"  V1: appended {len(appended)} clips")

    # --- V2-V4: overlays ------------------------------------------------------
    for idx in ([i for _, i, _ in OVERLAY_TRACKS]
                + [i for _, i, _, _, _ in MOTION_OVERLAYS]):
        while timeline.GetTrackCount("video") < idx:
            timeline.AddTrack("video")

    # recordFrame is ABSOLUTE, not relative to the start of the timeline. The timeline
    # begins at 01:00:00:00 - frame 108000 at 30 fps - so passing 0 here silently placed
    # every overlay a full hour before the footage, and they simply never appeared.
    origin = timeline.GetStartFrame()
    print(f"  timeline origin: frame {origin}")

    for fname, idx, label in OVERLAY_TRACKS:
        item = items[fname]
        frames = int(item.GetClipProperty("Frames"))
        ok = mp.AppendToTimeline([{
            "mediaPoolItem": item,
            "startFrame": 0,
            "endFrame": frames,
            "trackIndex": idx,
            "recordFrame": origin,
            "mediaType": 1,
        }])
        timeline.SetTrackName("video", idx, label)
        print(f"  V{idx}: {label:9} {frames} frames  {'ok' if ok else 'FAILED'}")

    # --- motion graphics ------------------------------------------------------
    by_section = {e.name: e for e in items_plan}
    for fname, idx, label, section, at_in in MOTION_OVERLAYS:
        entry = by_section.get(section)
        if entry is None:
            print(f"  V{idx}: {label:9} section {section!r} not in the plan  <-- SKIPPED")
            continue
        item = items[fname]
        avail = int(item.GetClipProperty("Frames"))
        # Trim to the section rather than trusting the render to be the same length: the
        # composition is authored to a round number of seconds, the cut is not.
        # Trimmed so it cannot run past the end of the section it belongs to.
        room = entry.frames - int(round(at_in * FPS))
        frames = min(avail, max(1, room))
        at = origin + int(round((entry.tl_start + at_in) * FPS))
        ok = mp.AppendToTimeline([{
            "mediaPoolItem": item,
            "startFrame": 0,
            "endFrame": frames,
            "trackIndex": idx,
            "recordFrame": at,
            "mediaType": 1,
        }])
        timeline.SetTrackName("video", idx, label)
        print(f"  V{idx}: {label:9} {frames} frames over {section!r} "
              f"+{at_in}s @ {at}  {'ok' if ok else 'FAILED'}")

    # --- sound effects --------------------------------------------------------
    if SFX_CUES:
        while timeline.GetTrackCount("audio") < SFX_TRACK:
            timeline.AddTrack("audio")
        for fname, anchor, off in SFX_CUES:
            entry = by_section.get(anchor)
            if entry is None:
                print(f"  A{SFX_TRACK}: {fname:12} anchor {anchor!r} not in plan  <-- SKIPPED")
                continue
            item = items[fname]
            # A WAV has no video frames, so GetClipProperty("Frames") reads 0 and the
            # append is silently a no-op. Length has to come from the file itself.
            dur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(SFX_DIR / fname)],
                capture_output=True, text=True, check=True).stdout.strip())
            frames = max(1, int(round(dur * FPS)))
            at = origin + int(round((entry.tl_start + off) * FPS))
            ok = mp.AppendToTimeline([{
                "mediaPoolItem": item,
                "startFrame": 0,
                "endFrame": frames,
                "trackIndex": SFX_TRACK,
                "recordFrame": at,
                "mediaType": 2,   # 2 = audio only
            }])
            print(f"  A{SFX_TRACK}: {fname:12} {frames:4d} frames @ {at} "
                  f"({anchor}{off:+.2f}s)  {'ok' if ok else 'FAILED'}")
        timeline.SetTrackName("audio", SFX_TRACK, "sfx")

    # --- recorded voiceover ---------------------------------------------------
    if VO_AUDIO:
        while timeline.GetTrackCount("audio") < VO_TRACK:
            timeline.AddTrack("audio")
        vo_dir = ROOT / "Trade" / "VOAudio"
        for entry in items_plan:
            stem = VO_AUDIO.get(entry.name)
            if entry.kind != "vo" or not stem:
                continue
            item = items[f"{stem}.wav"]
            frames = max(1, int(round(vo_duration(stem) * FPS)))
            at = origin + int(round((entry.tl_start + LEAD) * FPS))
            ok = mp.AppendToTimeline([{
                "mediaPoolItem": item,
                "startFrame": 0,
                "endFrame": frames,
                "trackIndex": VO_TRACK,
                "recordFrame": at,
                "mediaType": 2,
            }])
            print(f"  A{VO_TRACK}: {stem:14} {frames:4d} frames @ {at} "
                  f"({entry.name})  {'ok' if ok else 'FAILED'}")
        timeline.SetTrackName("audio", VO_TRACK, "voiceover")

    # --- music ----------------------------------------------------------------
    if MUSIC.exists():
        while timeline.GetTrackCount("audio") < MUSIC_TRACK:
            timeline.AddTrack("audio")
        item = items[MUSIC.name]
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(MUSIC)],
            capture_output=True, text=True, check=True).stdout.strip())
        frames = max(1, int(round(dur * FPS)))
        ok = mp.AppendToTimeline([{
            "mediaPoolItem": item,
            "startFrame": 0,
            "endFrame": frames,
            "trackIndex": MUSIC_TRACK,
            "recordFrame": origin,
            "mediaType": 2,
        }])
        timeline.SetTrackName("audio", MUSIC_TRACK, "music")
        print(f"  A{MUSIC_TRACK}: music        {frames} frames @ {origin}  "
              f"{'ok' if ok else 'FAILED'}")

    # --- read back ------------------------------------------------------------
    # Property writes report success generously; the readback is the truth.
    v1 = timeline.GetItemListInTrack("video", 1) or []
    print(f"\n{'section':22} {'expected':>9} {'actual':>7}")
    print("-" * 42)
    bad = 0
    for entry, it in zip(items_plan, v1):
        want, got = entry.frames, it.GetDuration()
        mark = "" if want == got else "  <-- MISMATCH"
        bad += bool(mark)
        print(f"{entry.name:22} {want:9d} {got:7d}{mark}")
    # Overlays are only useful if they actually sit over the cut - verify placement, not
    # just that the append call returned something truthy.
    for fname, idx, label in OVERLAY_TRACKS:
        got = timeline.GetItemListInTrack("video", idx) or []
        if len(got) != 1:
            print(f"  V{idx} {label}: expected 1 item, found {len(got)}  <-- MISMATCH")
        elif got[0].GetStart() != origin:
            print(f"  V{idx} {label}: starts at {got[0].GetStart()}, "
                  f"expected {origin}  <-- MISALIGNED")

    # Audio is easy to lose without noticing - the picture looks perfect either way.
    a_tracks = timeline.GetTrackCount("audio")
    a_items = sum(len(timeline.GetItemListInTrack("audio", i + 1) or [])
                  for i in range(a_tracks))
    want_audio = sum(1 for e in items_plan
                     if e.kind in ("footage", "blooper", "transition"))
    print(f"  audio: {a_tracks} track(s), {a_items} items "
          f"(expected {want_audio} from footage)"
          + ("" if a_items >= want_audio else "   <-- MISSING AUDIO"))

    total = sum(i.GetDuration() for i in v1)
    m, s = divmod(total / FPS, 60)
    print("-" * 42)
    print(f"{'TOTAL':22} {sum(e.frames for e in items_plan):9d} {total:7d}"
          f"   = {int(m)}:{s:04.1f}")
    if bad:
        print(f"\n{bad} clip(s) came back the wrong length - check the endFrame convention")

    # Save immediately: an unsaved project can raise a modal in the GUI that no script can
    # dismiss, which then blocks every later call.
    pm.SaveProject()
    print(f"\nsaved project {PROJECT!r}, timeline {TIMELINE!r}")


if __name__ == "__main__":
    main()
