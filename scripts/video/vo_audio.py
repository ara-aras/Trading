"""The recorded voiceover: which file belongs to which section, and how it is fitted.

Rafan and Prateek read faster than the 130 words per minute the gaps were budgeted at -
102 seconds of speech against 135 seconds of gap. Padding that out with silence would leave
half a minute of screen recording sitting there with nothing happening, so the gaps are
re-timed to the takes instead. The film gets about thirty seconds shorter, which is a gain.

Each section becomes: LEAD of picture before anyone speaks, the take, then TAIL before the
next transition starts. The lead matters - a graphic needs a beat to be read before a voice
starts over it - and the tail keeps the last word clear of the dip to black.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
VO_DIR = _ROOT / "Trade" / "VOAudio"

# Seconds of picture before the voice starts, and after it finishes.
LEAD = 0.50
TAIL = 0.70

# Section name in edl.CUTS -> stem in Trade/VOAudio.
VO_AUDIO: dict[str, str] = {
    "3 guards insert":  "vo_guards",
    "5 alpaca mleg":    "vo_mleg",
    "5 alpaca doctor":  "vo_doctor",
    "6 benchmark":      "vo_benchmark",
    "6 benchmark feed": "vo_feed",
    "9 close":          "vo_close",
}

# Whisper heard the takes accurately apart from these. Same rule as the on-camera captions:
# correct what was misheard, never "improve" what was said.
VO_CAPTION_FIXES: list[tuple[str, str, str]] = [
    ("vo_mleg", "Every order goes to Alpaca's", "Every order goes through Alpaca's"),
    ("vo_mleg", "the exact on that reason broker, CM leg",
     "the exact one that reached the broker. See m-leg"),
    ("vo_mleg", "CM leg", "m-leg"),
    ("vo_feed", "our rule book is", "our rulebook is"),
    ("vo_guards", "We don't ask another AI. If the first one lied, that",
     "We don't ask another AI if the first one lied. That"),
    ("vo_doctor", "Before, it builds an order", "Before it builds an order"),
    ("vo_doctor", "pointed at the paper account", "pointed at a paper account"),
]


@functools.lru_cache(maxsize=None)
def vo_duration(stem: str) -> float:
    p = VO_DIR / f"{stem}.wav"
    if not p.exists():
        return 0.0
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())
