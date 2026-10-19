"""Synthesise the sound effects rather than downloading them.

Every one of these is generated from ffmpeg's own oscillators and noise sources, so there is
no licence attached to any of it. That matters for a competition submission: a sound effect
grabbed off a search result carries whatever terms the uploader attached, which is usually
unknown and occasionally "all rights reserved", and nobody checks until it is a problem.

None of these is hard to synthesise anyway - a censor bleep is literally a 1 kHz sine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Trade" / "SFX"

SR = 48000


def build(name: str, filt: str, dur: float, gain_db: float = 0.0) -> Path:
    dst = OUT / f"{name}.wav"
    chain = filt
    if gain_db:
        chain += f",volume={gain_db}dB"
    # Everything ends stereo at 48k so it drops onto the timeline without conversion.
    chain += ",aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"anullsrc=r={SR}:cl=mono:d={dur:.3f}",
         "-filter_complex", f"[0:a]{chain}[a]", "-map", "[a]", "-t", f"{dur:.3f}",
         str(dst)],
        check=True,
    )
    return dst


def sine(freq: float, dur: float) -> str:
    return f"aevalsrc=sin(2*PI*{freq}*t):s={SR}:d={dur:.3f}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- censor bleep ---------------------------------------------------------
    # 1 kHz is the broadcast convention. The 8 ms fades matter: a sine cut dead at a
    # zero-crossing still clicks, and a click is more distracting than the word.
    for dur in (0.30, 0.45, 0.60, 0.90, 1.20):
        name = f"bleep_{int(dur * 100):03d}"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", f"sine=frequency=1000:sample_rate={SR}:duration={dur:.3f}",
             "-af", (f"afade=t=in:st=0:d=0.008,"
                     f"afade=t=out:st={dur - 0.008:.3f}:d=0.008,"
                     f"volume=-9dB,"
                     f"aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"),
             str(OUT / f"{name}.wav")],
            check=True,
        )
        print(f"  {name}.wav")

    # --- whoosh ---------------------------------------------------------------
    # Band-passed noise with a swell. Reads as a transition without being a cartoon.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"anoisesrc=color=brown:sample_rate={SR}:duration=0.85",
         "-af", ("bandpass=frequency=900:width_type=h:width=1400,"
                 "afade=t=in:st=0:d=0.35:curve=exp,"
                 "afade=t=out:st=0.45:d=0.40:curve=exp,"
                 "volume=-6dB,"
                 "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"),
         str(OUT / "whoosh.wav")],
        check=True,
    )
    print("  whoosh.wav")

    # --- title sting ----------------------------------------------------------
    # Two tones a fifth apart with a fast decay - a "ding" with a bit of body under it.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"sine=frequency=660:sample_rate={SR}:duration=1.1",
         "-f", "lavfi", "-i", f"sine=frequency=990:sample_rate={SR}:duration=1.1",
         "-filter_complex",
         ("[0:a]volume=-8dB[a];[1:a]volume=-14dB[b];[a][b]amix=inputs=2:normalize=0,"
          "afade=t=out:st=0.06:d=1.0:curve=exp,"
          "volume=-3dB,"
          "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo[out]"),
         "-map", "[out]", str(OUT / "sting.wav")],
        check=True,
    )
    print("  sting.wav")

    # --- soft pop -------------------------------------------------------------
    # For a quick cut between bloopers. Very short, low, easy to ignore.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency=220:sample_rate={SR}:duration=0.14",
         "-af", ("afade=t=out:st=0.01:d=0.13:curve=exp,volume=-16dB,"
                 "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"),
         str(OUT / "pop.wav")],
        check=True,
    )
    print("  pop.wav")


if __name__ == "__main__":
    main()
