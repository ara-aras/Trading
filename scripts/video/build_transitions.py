"""Render each transition as its own short clip.

Resolve's scripting API cannot add a transition. There is no AddTransition, and SetProperty
writes static values with no keyframes, so a dissolve cannot be built out of overlapping
clips and opacity either. The workable path is to render the blend as a normal clip and
drop it on the timeline between the two shots.

Each one behaves like a real dissolve: it takes its first half-second from the outgoing
shot's tail and the same from the incoming shot's head, which is why `plan()` trims both
neighbours by the transition length. On the timeline it is a separate item, so it can be
deleted or replaced with one of Resolve's own transitions by hand.

Audio crossfades across the join too, and silence is synthesised for the screen inserts so
the join never pops.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CUTS, FPS, TRANSITIONS, source_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Trade" / "Transitions"

W, H = 1920, 1080


def has_audio(path: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def render(name: str, kind: str, dur: float,
           a_path: Path, a_in: float, b_path: Path, b_in: float) -> Path:
    dst = OUT / f"{name}.mp4"
    frames = int(round(dur * FPS))

    # smoothfade is ours, not one of ffmpeg's named transitions: xfade's custom expression
    # with a smoothstep curve. Linear alpha spends the whole transition at a visible
    # half-and-half double exposure, which is precisely what makes a short dissolve look
    # cheap. P*P*(3-2P) eases in and out, so most of the duration sits near one shot or the
    # other and only the middle is genuinely mixed.
    if kind == "smoothfade":
        xfade = ("xfade=transition=custom:duration=%.3f:offset=0"
                 ":expr='A*(1-(P*P*(3-2*P)))+B*(P*P*(3-2*P))'" % dur)
    else:
        xfade = f"xfade=transition={kind}:duration={dur:.3f}:offset=0"

    cmd = ["ffmpeg", "-y", "-v", "error",
           "-ss", f"{a_in:.3f}", "-t", f"{dur + 0.2:.3f}", "-i", str(a_path),
           "-ss", f"{b_in:.3f}", "-t", f"{dur + 0.2:.3f}", "-i", str(b_path)]

    a_snd, b_snd = has_audio(a_path), has_audio(b_path)
    # xfade needs both sides identical in size, rate and pixel format, and it needs a
    # continuous timebase - setpts=PTS-STARTPTS after a seek is what gives it one.
    fc = [
        f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p,setsar=1,setpts=PTS-STARTPTS[va]",
        f"[1:v]scale={W}:{H},fps={FPS},format=yuv420p,setsar=1,setpts=PTS-STARTPTS[vb]",
        f"[va][vb]{xfade}[v]",
    ]

    n = 2
    if a_snd:
        fc.append("[0:a]aresample=48000,asetpts=PTS-STARTPTS[aa]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur + 0.2:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        fc.append(f"[{n}:a]asetpts=PTS-STARTPTS[aa]")
        n += 1
    if b_snd:
        fc.append("[1:a]aresample=48000,asetpts=PTS-STARTPTS[ab]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur + 0.2:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        fc.append(f"[{n}:a]asetpts=PTS-STARTPTS[ab]")
    fc.append(f"[aa][ab]acrossfade=d={dur:.3f}:c1=tri:c2=tri[a]")

    cmd += ["-filter_complex", ";".join(fc),
            "-map", "[v]", "-map", "[a]",
            "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            str(dst)]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{name}: {r.stderr.strip()[-400:]}")
    return dst


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{'name':20} {'kind':10} {'dur':>5} {'from':18} -> {'to':18}")
    print("-" * 82)

    for i, cut in enumerate(CUTS):
        if cut.section not in TRANSITIONS:
            continue
        kind, dur = TRANSITIONS[cut.section]
        nxt = CUTS[i + 1]
        name = f"t{i:02d}_{kind}"

        dst = render(
            name, kind, dur,
            source_path(cut), cut.end - dur,
            source_path(nxt), nxt.start,
        )
        got = int(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(dst)],
            capture_output=True, text=True,
        ).stdout.strip() or 0)
        want = int(round(dur * FPS))
        flag = "" if got == want else f"  <-- {got} frames, wanted {want}"
        print(f"{name:20} {kind:10} {dur:5.2f} {cut.section:18} -> {nxt.section:18}{flag}")


if __name__ == "__main__":
    main()
