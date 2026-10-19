"""Render the chapter cards that sit between sections.

Why these exist at all: a cross-dissolve between two talking-head shots in different
locations superimposes both faces for the length of the blend. Frame-stepping the old
transition shows Prateek and Rafan ghosted over each other for most of a second, which is
what made the joins feel wrong - and easing the curve cannot fix it, because the problem is
that both images are on screen at once.

So the section joins stop being dissolves. They dip to black, hold a designed card naming
what comes next, and dip back up. That is how documentary handles exactly this join, it
reads as deliberate rather than as a mistake, and it gives a judge a moment to re-orient.

The cards are static by design apart from a slow push. The fades either side are the
`fadeblack` transitions in edl.TRANSITIONS, not baked in here, so the card itself is clean
paper end to end and the two mechanisms cannot double up.

Design follows the same editorial system as the full-screen cycle graphic: paper ground,
ink and cobalt, one hairline rule, heavy Helvetica against small tracked uppercase. No
gradients, no glow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edl import CHAPTERS, FPS  # noqa: E402
from record_captures import _launch_system_browser  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Trade" / "Chapters"
PAGES = ROOT / "Trade" / "ChapterPages"

W, H = 1920, 1080

CARD = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1920px; height:1080px; overflow:hidden; background:#f2f0ea;
    font-family: Helvetica, Arial, sans-serif; }}
  .frame {{ position:absolute; inset:0; padding:96px 110px;
    display:flex; flex-direction:column; justify-content:center; }}
  .rail {{ position:absolute; left:110px; top:96px; bottom:96px; width:3px;
    background:#0a4fd3; }}
  .inner {{ padding-left:64px; }}
  .num {{ font-family:Consolas,monospace; font-size:20px; letter-spacing:.42em;
    text-transform:uppercase; color:#10161f; opacity:.5; }}
  .title {{ margin-top:22px; font-family:"Arial Black",Helvetica,sans-serif;
    font-size:104px; line-height:.98; letter-spacing:-.022em; color:#10161f; }}
  .rule {{ margin-top:34px; width:210px; height:4px; background:#0a4fd3; }}
  .sub {{ margin-top:30px; max-width:1020px; font-size:26px; line-height:1.5;
    color:#10161f; opacity:.66; }}
  .slug {{ position:absolute; left:110px; right:110px; bottom:74px;
    font-family:Consolas,monospace; font-size:16px; letter-spacing:.30em;
    text-transform:uppercase; color:#10161f; opacity:.38;
    display:flex; justify-content:space-between; }}
</style></head><body>
  <div class="frame">
    <div class="rail"></div>
    <div class="inner">
      <div class="num">{num}</div>
      <div class="title">{title}</div>
      <div class="rule"></div>
      <div class="sub">{sub}</div>
    </div>
  </div>
  <div class="slug"><span>Brightline</span><span>{right}</span></div>
</body></html>
"""


def shoot(page, name: str, num: str, title: str, sub: str, right: str) -> Path:
    html = PAGES / f"{name}.html"
    html.write_text(
        CARD.format(num=num, title=title, sub=sub, right=right), encoding="utf-8"
    )
    png = PAGES / f"{name}.png"
    page.goto(html.as_uri(), wait_until="networkidle")
    page.screenshot(path=str(png))
    return png


def animate(png: Path, dst: Path, seconds: float) -> None:
    """Still to clip, with a slow push so the card is not a frozen frame."""
    frames = int(round(seconds * FPS))
    # Scale up first, then zoompan across the oversampled image - zooming a 1080p still
    # directly makes the type crawl and shimmer.
    vf = (
        f"scale={W * 2}:{H * 2},"
        f"zoompan=z='1+0.016*on/{frames}':d={frames}:s={W}x{H}:fps={FPS},"
        f"setsar=1,format=yuv420p"
    )
    # Both inputs first, then the output options. A -vf sitting between two -i arguments
    # is parsed as an option on the NEXT input, and ffmpeg rejects it.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-loop", "1", "-i", str(png),
         "-f", "lavfi", "-t", f"{seconds:.3f}",
         "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-c:a", "aac", "-b:a", "128k", "-shortest", str(dst)],
        check=True,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = _launch_system_browser(p)
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  device_scale_factor=1)
        page = ctx.new_page()
        for i, ch in enumerate(CHAPTERS, start=1):
            name = ch["src"]
            png = shoot(page, name, f"Chapter {i:02d}" if ch.get("num", True) else "",
                        ch["title"], ch["sub"], ch["right"])
            animate(png, OUT / f"{name}.mp4", ch["dur"])
            print(f"  {name:22} {ch['dur']:.1f}s  {ch['title']}")
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
