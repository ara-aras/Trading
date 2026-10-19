"""Build the burned-in caption and graphics overlays as alpha movs for Resolve.

Three separate overlays, so any one can be swapped or switched off without re-rendering
the others:

  captions.mov  word-by-word captions for everything spoken on camera
  vo_guide.mov  the script lines Rafan still has to dub, shown over the screen inserts
  graphics.mov  title card and the two stamps

The end card is not here. It used to be text on graphics.mov; it is now the poster, which
is a full-frame image rather than type, so build_endcard.py renders it and add_endcard.py
puts it on its own track above these.

All three are QuickTime RLE with a real alpha channel. ProRes 4444 would be the usual
choice, but at 1080p30 it runs ~330 Mbit/s, which is about 12 GB for a five-minute overlay
that is mostly empty frames. RLE is lossless and compresses transparency to nearly nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CAPTION_FIXES, FPS, audio_shift, plan, transcript_dir  # noqa: E402
from censor_bloopers import PROFANITY, mask, strip_word  # noqa: E402
from vo_audio import LEAD, VO_AUDIO, VO_CAPTION_FIXES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPTS = ROOT / "Trade" / "Transcripts"
OUT = ROOT / "Trade" / "Overlays"

W, H = 1920, 1080

# How long the end card holds at the tail of the close section.
END_CARD_SECS = 6.0

# Cyan reads as "system output" next to the dashboard and the capture pages, and stays
# legible over both the bright lab wall and the dark inserts. ASS colours are &HBBGGRR.
ACCENT = "&H00FAC85A"
WHITE = "&H00FFFFFF"
RED = "&H002020E8"

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Segoe UI Black,64,{WHITE},{WHITE},&H00101010,&H80000000,0,0,0,0,100,100,0.6,0,1,5.5,2.5,2,180,180,96,1
Style: VO,Consolas,40,&H00C8C8C8,&H00C8C8C8,&H00101010,&HA0000000,0,0,0,0,100,100,0,0,1,3.5,0,2,140,140,86,1
Style: Scrim,Arial,20,&H00000000,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Title,Segoe UI Black,150,{WHITE},{WHITE},&H00101010,&H00000000,0,0,0,0,100,100,10,0,1,0,0,5,80,80,80,1
Style: Sub,Segoe UI Black,40,&H00F0F0F0,&H00F0F0F0,&H00101010,&H00000000,0,0,0,0,100,100,4,0,1,3,0,5,80,80,80,1
Style: Stamp,Segoe UI Black,110,{RED},{RED},&H00FFFFFF,&H00000000,0,0,0,0,100,100,6,0,1,5,0,5,80,80,80,1
Style: End,Consolas,42,{WHITE},{WHITE},&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,3,0,5,80,80,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t: float) -> str:
    if t < 0:
        t = 0.0
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ev(style: str, start: float, end: float, text: str, layer: int = 0) -> str:
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}"


def scrim(start: float, end: float, y0: int = 0, y1: int = H,
          alpha: str = "2E", layer: int = 1) -> str:
    """A dark band drawn behind text, so cards stay legible over bright footage.

    The cold open and the close were shot outdoors against sunlit foliage; white type on
    that is unreadable without something behind it.
    """
    box = rf"{{\p1\an7\pos(0,0)\c&H000000&\alpha&H{alpha}&\fad(260,300)}}" \
          rf"m 0 {y0} l {W} {y0} {W} {y1} 0 {y1}"
    return f"Dialogue: {layer},{ts(start)},{ts(end)},Scrim,,0,0,0,,{box}"


# --- timeline geometry --------------------------------------------------------


def timeline_offsets() -> list[tuple[object, float]]:
    """Each plan item paired with the timeline second it starts at.

    Read from plan(), not CUTS, so transitions are accounted for - they shorten both
    neighbours, which moves every position after the first one.
    """
    return [(e, e.tl_start) for e in plan()]


# --- captions -----------------------------------------------------------------


def _fix_text(stem: str, text: str, table=None) -> str:
    for clip, wrong, right in (CAPTION_FIXES if table is None else table):
        if clip == stem and wrong in text:
            text = text.replace(wrong, right)
    return text


def _segment_words(stem: str, seg: dict, table=None) -> list[tuple[str, float, float]]:
    """Words for one segment, after corrections, with timings that survive a reword.

    Where a correction changes the word count - "runs on 4 cycles" becoming "runs one
    cycle" - the original per-word timings no longer line up, so the corrected words are
    spread evenly across the segment instead. The segment boundaries are what matter for
    sync; a few tens of milliseconds inside it are not noticeable.
    """
    raw = [w for w in seg.get("words", []) if w.get("word", "").strip()]
    fixed = _fix_text(stem, seg["text"], table).strip()
    tokens = [t for t in re.split(r"\s+", fixed) if t]
    if not tokens:
        return []

    if len(tokens) == len(raw):
        return [(t, w["start"], w["end"]) for t, w in zip(tokens, raw)]

    s, e = float(seg["start"]), float(seg["end"])
    step = (e - s) / len(tokens)
    return [(t, s + i * step, s + (i + 1) * step) for i, t in enumerate(tokens)]


def _phrases(words: list[tuple[str, float, float]], max_words=4, max_gap=0.7):
    """Group words into short on-screen phrases.

    Four words at a time is the readable maximum at this size, and a pause longer than
    max_gap is treated as a natural break so a caption never straddles a beat.
    """
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[1] - cur[-1][2] > max_gap):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def build_captions() -> Path:
    """Word-by-word captions: whole phrase visible, active word lit and slightly larger."""
    lines = []
    for cut, offset in timeline_offsets():
        # The voiceover is captioned from its own recordings, and sits LEAD seconds into
        # its section - so it is timed against the take, not against any picture.
        if cut.kind == "vo" and cut.name in VO_AUDIO:
            stem = VO_AUDIO[cut.name]
            jf = ROOT / "Trade" / "VOTranscripts" / f"{stem}.json"
            if jf.exists():
                data = json.loads(jf.read_text(encoding="utf-8"))
                words = []
                for seg in data["segments"]:
                    words.extend(_segment_words(stem, seg, VO_CAPTION_FIXES))
                words = [(t, offset + LEAD + a, offset + LEAD + b) for t, a, b in words]
                lines.extend(_emit(words))
            continue

        if cut.kind not in ("footage", "blooper"):
            continue
        jf = transcript_dir(cut.kind) / f"{cut.src}.json"
        if not jf.exists():
            continue
        data = json.loads(jf.read_text(encoding="utf-8"))

        words: list[tuple[str, float, float]] = []
        for seg in data["segments"]:
            words.extend(_segment_words(cut.src, seg))

        # Whisper timed these against a WAV, which starts at the first audio sample. The
        # same shift that puts the audio in sync therefore has to be applied to the word
        # timings, or the captions drift away from the words the instant sync is corrected.
        # Bloopers were conformed with their offset already baked in as leading silence, and
        # their transcripts were taken from those conformed files - so their timings are
        # against picture already and must not be shifted again.
        shift = 0.0 if cut.kind == "blooper" else audio_shift(cut.src)
        if shift:
            words = [(t, s + shift, e + shift) for t, s, e in words]

        # Bleeping the audio while the caption spells the word out defeats the point.
        if cut.kind == "blooper":
            words = [(mask(strip_word(t)) if PROFANITY.match(strip_word(t)) else t, s, e)
                     for t, s, e in words]

        # Keep only what this item actually shows, and rebase onto the timeline. The in/out
        # here are the post-transition trims, so a caption never survives into a dissolve
        # that has already cut away from the speaker.
        words = [w for w in words if cut.start <= w[1] < cut.end]
        words = [(t, offset + s - cut.start, offset + min(e, cut.end) - cut.start)
                 for t, s, e in words]

        lines.extend(_emit(words))

    p = OUT / "captions.ass"
    p.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"  captions.ass       {len(lines):4d} events")
    return p


def _emit(words) -> list[str]:
    """Phrase grouping and the word-by-word highlight, shared by every caption source."""
    lines: list[str] = []
    for phrase in _phrases(words):
        for i, (_, ws, we) in enumerate(phrase):
            parts = []
            for j, (tok, _, _) in enumerate(phrase):
                esc = tok.replace("{", "(").replace("}", ")")
                if j == i:
                    parts.append(
                        rf"{{\c{ACCENT}\fscx106\fscy106}}{esc}{{\c{WHITE}\fscx100\fscy100}}"
                    )
                else:
                    parts.append(esc)
            fade = r"\fad(90,0)" if i == 0 else (
                r"\fad(0,110)" if i == len(phrase) - 1 else "")
            body = ("{" + fade + "}" if fade else "") + " ".join(parts)
            end = phrase[i + 1][1] if i + 1 < len(phrase) else we
            lines.append(ev("Cap", ws, max(end, ws + 0.06), body))
    return lines


# --- VO guide -----------------------------------------------------------------


def build_vo_guide() -> Path:
    """The lines Rafan still has to record, held over the matching screen insert."""
    lines = []
    for cut, offset in timeline_offsets():
        if cut.kind != "vo" or not (cut.cut and cut.cut.vo_text):
            continue
        a, b = offset + 0.3, offset + cut.duration - 0.2
        # The end card occupies the last END_CARD_SECS of the close section; clear the
        # guide text out before it arrives so the two don't print over each other.
        if cut.name == "9 close":
            b = offset + cut.duration - END_CARD_SECS - 0.4
        # Bottom of frame, not top: the screen inserts all carry their own heading up there,
        # and the guide text was landing straight on top of it. Nothing speaks during a VO
        # section, so the caption track is empty here and the bottom is free.
        lines.append(scrim(a, b, y0=800, y1=1080, alpha="26"))
        body = cut.cut.vo_text.replace("\n", r"\N")
        lines.append(
            # Layer 2, above the scrim on layer 1 - ASS paints higher layers last, so a
            # layer-0 caption sits *underneath* its own backing and washes out.
            ev("VO", a, b,
               r"{\fad(200,200)}{\fs27\b1\c" + ACCENT + r"}VOICEOVER — TO RECORD"
               r"{\r}\N" + body, layer=2)
        )
    p = OUT / "vo_guide.ass"
    p.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"  vo_guide.ass       {len(lines):4d} events")
    return p


# --- graphics -----------------------------------------------------------------


def build_graphics() -> Path:
    """Title card, the two stamps, and the end card, placed against the real cut."""
    entries = {e.name: e for e in plan()}
    at = {name: e.tl_start for name, e in entries.items()}
    lines = []

    # Title card - lands on "That's Brightline", ~19.7s into Prateek's take.
    t0 = at["1 cold open"] + 17.3
    lines += [
        scrim(t0, t0 + 3.6, alpha="4A"),
        ev("Title", t0, t0 + 3.6,
           r"{\fad(280,320)\pos(960,500)\t(0,600,\fscx104\fscy104)}BRIGHTLINE", layer=2),
        ev("Sub", t0 + 0.55, t0 + 3.6,
           r"{\fad(420,320)\pos(960,640)}a bright-line rule admits no judgment. "
           r"neither does ours.", layer=2),
    ]

    # UNVERIFIED - over "make up its own rules". Snaps in slightly rotated, like a stamp.
    t1 = at["1 cold open"] + 8.4
    lines.append(
        ev("Stamp", t1, t1 + 2.3,
           r"{\fad(90,260)\frz9\pos(1290,300)\t(0,180,\fscx100\fscy100)"
           r"\fscx160\fscy160}UNVERIFIED", layer=2)
    )

    # REJECTED - over the collapse, which is where the trade dies.
    # Anchored to the moment in the source - he goes down at ~21.0s - rather than to a clip
    # boundary, so re-trimming the shot cannot slide the stamp off the collapse.
    poisoned = entries["3 bottle poisoned"]
    t2 = poisoned.tl_start + (21.35 - poisoned.start)
    lines.append(
        ev("Stamp", t2, t2 + 2.4,
           r"{\fad(80,300)\frz-7\pos(960,470)\t(0,170,\fscx100\fscy100)"
           r"\fscx165\fscy165}REJECTED", layer=2)
    )

    # No end card here any more. It used to be a BRIGHTLINE wordmark plus the team and
    # account lines burned in over the close, and it is now the poster itself - a
    # full-frame image, so it cannot be an ASS event. See build_endcard.py, which renders
    # it, and build_resolve_timeline.py, which places it on its own track from the same
    # END_CARD_SECS. Anything drawn here in that window would sit underneath it anyway.

    # The bloopers title used to live here as burned-in text. It is now chapter card
    # ch08 on V1, which is the same design system as the rest - keeping both would
    # print the word twice.

    p = OUT / "graphics.ass"
    p.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"  graphics.ass       {len(lines):4d} events")
    return p


# --- render -------------------------------------------------------------------


def render(ass: Path, seconds: float) -> Path:
    """Burn one .ass onto transparency and encode it as an alpha mov."""
    mov = ass.with_suffix(".mov")
    # ffmpeg's subtitles filter wants a POSIX-ish path with the drive colon escaped.
    esc = str(ass).replace("\\", "/").replace(":", r"\:")
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i",
            f"color=c=black@0.0:s={W}x{H}:r={FPS}:d={seconds:.3f},format=rgba",
            "-vf", f"subtitles='{esc}':alpha=1",
            "-c:v", "qtrle", "-pix_fmt", "argb",
            str(mov),
        ],
        check=True,
    )
    mb = mov.stat().st_size / 1e6
    print(f"  {mov.name:18} {mb:7.1f} MB")
    return mov


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    total = sum(e.duration for e in plan())
    print(f"timeline: {total:.2f}s")
    # build_vo_guide() is deliberately not called any more: the voiceover has been
    # recorded, so the on-screen prompt track has done its job. The function stays
    # for a future re-record.
    for ass in (build_captions(), build_graphics()):
        render(ass, total)
