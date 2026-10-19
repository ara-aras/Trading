"""Build the background music bed, ducked under the dialogue.

The ducking is done with a real sidechain compressor keyed off the finished mix, not with a
fixed level or a hand-drawn envelope. That matters: the cut has on-camera dialogue, recorded
voiceover, sound effects and long stretches of screen recording with nobody speaking at all.
A fixed level that sits nicely under a voice is far too loud in the gaps, and a level that
works in the gaps disappears under the voice.

Keying off the render means the music gets out of the way of whatever is actually audible at
that moment, including the bloopers, and comes back up on its own in the silences.

The bed is then placed on its own track in Resolve, so its level stays adjustable by hand.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
BG_DIR = ROOT / "Trade" / "BG"
OUT = ROOT / "Trade" / "Music"
REFERENCE = ROOT / "Trade" / "Outputs" / "brightline-rough-cut.mp4"

# Music level when nothing else is playing. Quiet enough to sit under a film rather than
# score it - this is a bed, not a soundtrack.
BED_LUFS = -30.0

# How hard the compressor pulls the music down when someone speaks, and how quickly it
# recovers. 900 ms release is slow enough that it does not pump between words.
RATIO = 12
ATTACK_MS = 20
RELEASE_MS = 900
THRESHOLD = 0.015


def source_track() -> Path:
    tracks = [p for p in BG_DIR.iterdir()
              if p.suffix.lower() in {".webm", ".mp3", ".wav", ".m4a", ".ogg", ".opus"}]
    if not tracks:
        raise SystemExit(f"no music found in {BG_DIR}")
    if len(tracks) > 1:
        print(f"  {len(tracks)} tracks present, using {tracks[0].name}")
    return tracks[0]


def duration(p: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not REFERENCE.exists():
        raise SystemExit(f"need a rendered cut to key the ducking off: {REFERENCE}")

    src = source_track()
    need = duration(REFERENCE)
    have = duration(src)
    print(f"  music : {src.name}")
    print(f"  length: {have:.1f}s available, {need:.1f}s needed "
          f"({'loops' if have < need else 'trimmed'})")

    # Loop to length. -stream_loop repeats the input; the trim to `need` happens on output,
    # and the seam is covered by the fact that this sits ~30 LUFS down under dialogue.
    loops = max(0, int(need // have))
    bed = OUT / "bed_raw.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-stream_loop", str(loops), "-i", str(src),
         "-t", f"{need:.3f}",
         "-af", f"loudnorm=I={BED_LUFS}:TP=-3:LRA=11,aresample=48000",
         "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(bed)],
        check=True,
    )

    # Sidechain: the finished mix ducks the music. amix would just sum them, so the two are
    # fed to sidechaincompress with the film as the key input and only the music kept.
    ducked = OUT / "music_ducked.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-i", str(bed), "-i", str(REFERENCE),
         "-filter_complex",
         (f"[1:a]aresample=48000,highpass=f=120,alimiter=limit=0.9[key];"
          f"[0:a][key]sidechaincompress="
          f"threshold={THRESHOLD}:ratio={RATIO}:attack={ATTACK_MS}:release={RELEASE_MS}"
          f":makeup=1:detection=rms[duck];"
          # Ease in and out so the music never starts or stops abruptly.
          f"[duck]afade=t=in:st=0:d=2.5,afade=t=out:st={need - 3.0:.3f}:d=3.0,"
          f"aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo[out]"),
         "-map", "[out]", "-t", f"{need:.3f}", str(ducked)],
        check=True,
    )
    bed.unlink(missing_ok=True)

    def lufs(p: Path) -> str:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(p), "-af",
             "loudnorm=print_format=json", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        blob = r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1]
        import json
        return json.loads(blob)["input_i"]

    print(f"  bed   : {ducked.name}  {duration(ducked):.1f}s  {lufs(ducked)} LUFS integrated")
    print(f"  film  : {lufs(REFERENCE)} LUFS integrated")


if __name__ == "__main__":
    main()
