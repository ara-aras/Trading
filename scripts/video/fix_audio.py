"""Rebuild each conformed clip's audio: aligned to picture, and levelled.

Two things are wrong with the audio as shot.

Alignment. Two separate problems, combined into one number by edl.audio_shift(): the
container's own audio start offset, and the Bluetooth headset latency that the camera never
compensated for. The latency does not appear in any metadata - it had to be measured off the
picture (see measure_sync.py) - and it is the larger of the two, up to 733 ms. The result is
baked in here as real leading silence or a real head trim, so the audio is in sync by
construction rather than by an edit list some tool might ignore.

Level. The takes run from -12 to -32 LUFS - a 20 dB step between adjacent shots, which is
far more noticeable than any of the picture differences. Two-pass loudnorm brings them all
to a common target; the second pass is what makes it accurate rather than approximate.

Video is copied through untouched, so this does not re-encode picture or undo the conform.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CUTS, LUFS_TARGET, audio_shift  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONFORMED = ROOT / "Trade" / "Conformed"
# Written alongside rather than over the conform: Resolve holds the imported files
# open, so replacing them in place fails with a permission error mid-run.
SYNCED = ROOT / "Trade" / "Synced"


def measure(path: Path) -> dict:
    """Pass one: what loudnorm needs to know to hit the target exactly."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af",
         f"loudnorm=I={LUFS_TARGET}:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    blob = r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1]
    return json.loads(blob)


def main() -> None:
    SYNCED.mkdir(parents=True, exist_ok=True)
    stems = sorted({c.src for c in CUTS if c.kind == "footage"})
    print(f"{'clip':18} {'shift':>7} {'in LUFS':>8} {'out LUFS':>9}")
    print("-" * 46)

    for stem in stems:
        src = CONFORMED / f"{stem}.mp4"
        if not src.exists():
            print(f"{stem:18}  MISSING {src}")
            continue

        shift = audio_shift(stem)
        m = measure(src)

        dst = SYNCED / f"{stem}.mp4"
        chain = []
        if shift > 0.001:
            ms = int(round(shift * 1000))
            chain.append(f"adelay={ms}|{ms}")
        elif shift < -0.001:
            # Negative shift means the audio is late and has to be pulled earlier, which
            # means discarding that much from the head. adelay cannot take a negative value.
            chain.append(f"atrim=start={abs(shift):.3f},asetpts=PTS-STARTPTS")
        chain.append(
            f"loudnorm=I={LUFS_TARGET}:TP=-1.5:LRA=11"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true:print_format=summary"
        )
        chain.append("aresample=48000")

        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src),
             # Drop the container offset: it is now real silence in the samples instead.
             "-af", ",".join(chain),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", str(dst)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"{stem:18}  FAILED: {r.stderr.strip()[:120]}")
            dst.unlink(missing_ok=True)
            continue

        after = measure(dst)
        print(f"{stem:18} {shift:7.3f} {float(m['input_i']):8.1f} "
              f"{float(after['input_i']):9.1f}")

    # The menu scene's crop copies audio through, so it has to be redone from the new source.
    print("\nre-running the crop so the menu scene picks up its fixed audio:")
    subprocess.run([sys.executable, str(Path(__file__).with_name("prep_footage.py"))],
                   check=True)


if __name__ == "__main__":
    main()
