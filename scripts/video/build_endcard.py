"""Render the poster as the end card, as an alpha mov Resolve lays over the close.

The end card used to be burned-in ASS text - a BRIGHTLINE wordmark plus the team and
account lines. The poster says all of that already, in the branding the submission is
judged next to, so the text version is gone and this takes its place.

Poster.jpg is 1600x900 - exactly 16:9, so it scales to 1080p without cropping or pillars.
Upscaled with lanczos rather than the default bicubic, because the poster is mostly
hard-edged type on flat colour, which is where the difference shows.

The captions are burned in here too, and that is the whole reason this is not just an
image on a track. The old card was a semi-transparent scrim, so the closing captions read
straight through it. The poster is opaque and sits above the caption track, which would
have buried the last 4.7 seconds of narration - the close is still talking until 271.7s.
Compositing the captions on top of the poster inside this render puts them back. The same
words are still on V2 underneath, drawn behind the poster and therefore invisible, so
nothing is doubled on screen.

ProRes 4444 rather than the QuickTime RLE the other overlays use. RLE is the right choice
for overlays that are mostly transparent - it compresses empty frames to nothing - but this
one is a full-frame photographic image on every frame, where RLE is close to uncompressed
(about 1.5 GB for six seconds). ProRes 4444 carries the alpha just as losslessly for the
fades and lands around a quarter of that.

The alpha fades let the shot underneath show through at both ends, so the card arrives and
leaves the way the text one did instead of hard-cutting in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import FPS, plan  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
POSTER = ROOT / "Trade" / "Poster.jpg"
CAPTIONS = ROOT / "Trade" / "Overlays" / "captions.ass"
OUT = ROOT / "Trade" / "Overlays" / "endcard.mov"

W, H = 1920, 1080

# Kept in step with END_CARD_SECS in build_overlays.py - the card occupies the tail of the
# close section, and add_endcard.py positions it from the same number.
SECONDS = 6.0
FADE_IN = 0.5
FADE_OUT = 0.6

SECTION = "9 close"

# The captions ride lower over the card than they do over footage. At their normal height
# they land squarely on the poster's headline figures - 203+ cycles, 153 tests, 2% risk -
# which is the one row on it worth reading. Dropped to the bottom edge they cover only the
# strapline, over a scrim the same weight as the ones used elsewhere in the film.
CAPTION_MARGIN_V = 24
SCRIM_H = 118
SCRIM_ALPHA = 0.55


def start_time() -> float:
    """The timeline second the card comes up, read from the cut rather than hardcoded."""
    entry = next((e for e in plan() if e.name == SECTION), None)
    if entry is None:
        raise SystemExit(f"{SECTION!r} is not in the plan")
    return entry.tl_start + entry.duration - SECONDS


def lowered_captions() -> Path:
    """A copy of captions.ass with the Cap style sitting at the bottom edge.

    Only the last field of the style line - MarginV - changes; everything else about the
    captions, including the per-word colouring, stays exactly as it is on V2 so the two
    cannot drift apart.
    """
    out = CAPTIONS.with_name("captions_endcard.ass")
    lines = []
    for ln in CAPTIONS.read_text(encoding="utf-8").splitlines():
        if ln.startswith("Style: Cap,"):
            f = ln.split(",")
            f[-2] = str(CAPTION_MARGIN_V)      # MarginV, second from last before Encoding
            ln = ",".join(f)
        lines.append(ln)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    for p in (POSTER, CAPTIONS):
        if not p.exists():
            raise SystemExit(f"missing input: {p}")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    t0 = start_time()
    ass = lowered_captions()
    # ffmpeg's subtitles filter wants a POSIX-ish path with the drive colon escaped.
    esc = str(ass).replace("\\", "/").replace(":", r"\:")

    # The canvas runs from zero so the subtitle timestamps land where the .ass says they
    # do; the window is cut out afterwards with trim. Rendering only the tail with -ss
    # would restart the clock at zero and pull in whichever captions happened to be first.
    # The fades are timed against the poster's OWN clock, which runs 0..SECONDS, and the
    # shift onto the timeline clock happens after. Fading with absolute times before the
    # shift asks for a fade-in at 267s on a stream that ends at 6s, so it never starts and
    # the card stays fully transparent for its whole length - an end card of nothing but
    # captions.
    graph = (
        f"[1:v]scale={W}:{H}:flags=lanczos,"
        f"drawbox=x=0:y={H - SCRIM_H}:w={W}:h={SCRIM_H}:"
        f"color=black@{SCRIM_ALPHA}:t=fill,format=rgba,"
        f"fade=t=in:st=0:d={FADE_IN}:alpha=1,"
        f"fade=t=out:st={SECONDS - FADE_OUT:.3f}:d={FADE_OUT}:alpha=1,"
        f"setpts=PTS+{t0:.3f}/TB[card];"
        f"[0:v][card]overlay=eof_action=pass:shortest=0[bg];"
        f"[bg]subtitles='{esc}':alpha=1,"
        f"trim=start={t0:.3f}:end={t0 + SECONDS:.3f},setpts=PTS-STARTPTS,"
        f"format=yuva444p10le[out]"
    )

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i",
         f"color=c=black@0.0:s={W}x{H}:r={FPS}:d={t0 + SECONDS:.3f},format=rgba",
         "-loop", "1", "-t", f"{SECONDS:.3f}", "-i", str(POSTER),
         "-filter_complex", graph, "-map", "[out]",
         "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
         str(OUT)],
        check=True,
    )

    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,pix_fmt,nb_read_frames",
         "-of", "csv=p=0", str(OUT)],
        capture_output=True, text=True, check=True).stdout.strip()
    print(f"  {OUT.name:14} starts {t0:.2f}s  {OUT.stat().st_size / 1e6:7.1f} MB  {info}")


if __name__ == "__main__":
    main()
