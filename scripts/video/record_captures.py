"""Record the video's screen-capture inserts headlessly.

Headless Chromium rather than a desktop grab, for three reasons the video needs: there is
no mouse cursor in the frame at all, the framing is identical on every re-run, and nothing
else on the machine can wander into shot. Output is 1920x1080 to match the conformed
footage, so Resolve never has to rescale an insert.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGES = (ROOT / "Trade" / "CapturePages").as_uri().rstrip("/")
OUT = ROOT / "Trade" / "Captures"
RAW = OUT / "_raw"
DASH = "http://localhost:3000"

W, H = 1920, 1080

# The script's hard rule: the Alpaca key panel never reaches a frame. Belt and braces on top
# of the redaction already done in build_capture_pages.py, since this recorder also films the
# live dashboard, where a future panel could appear without anyone remembering this file.
REDACT_CSS = """
  input[type=password], [data-secret], [aria-label*="key" i], [class*="apikey" i],
  [class*="api-key" i], [id*="apikey" i] { filter: blur(14px) !important; }
"""


def _launch_system_browser(p, **kw):
    """Launch an installed Chrome/Edge, falling back to the bundled Chromium.

    Order matters only in that both system browsers are Chromium under the hood, so the
    rendering is the same; we just need one that actually starts.
    """
    last = None
    for channel in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=channel, **kw)
        except Exception as exc:
            last = exc
    try:
        return p.chromium.launch(**kw)
    except Exception:
        raise RuntimeError(f"no usable browser; last channel error: {last}")


def smooth_scroll(page, selector: str, to: int, ms: int) -> None:
    """Travel content by `to` pixels over `ms`, eased, driven in-page.

    The capture pages move a transform rather than scrollTop: their scroller is absolutely
    positioned inside an overflow:hidden viewport, which has no scrollport, so setting
    scrollTop on it does nothing at all. The live dashboard is a real document and still
    uses window scrolling.
    """
    page.evaluate(
        """([sel, to, ms]) => new Promise(res => {
             const win = sel === 'window';
             const el = win ? document.scrollingElement : document.querySelector(sel);
             if (!el) { res(); return; }
             const read = () => win ? el.scrollTop
               : -(new DOMMatrixReadOnly(getComputedStyle(el).transform).m42);
             const from = read(), d = to - from, t0 = performance.now();
             // easeInOutSine: starts and stops without a jolt, which reads as camera move
             // rather than as a scrollbar being dragged.
             const ease = p => -(Math.cos(Math.PI * p) - 1) / 2;
             function step(t) {
               const p = Math.min(1, (t - t0) / ms), v = from + d * ease(p);
               if (win) el.scrollTop = v;
               else el.style.transform = `translateY(${-v}px)`;
               if (p < 1) requestAnimationFrame(step); else res();
             }
             requestAnimationFrame(step);
           })""",
        [selector, to, ms],
    )


def record(name: str, url: str, plan, settle: float = 1.2):
    """Film one insert. `plan` receives the page and drives whatever motion it needs."""
    RAW.mkdir(parents=True, exist_ok=True)
    stage = RAW / name
    if stage.exists():
        shutil.rmtree(stage)

    with sync_playwright() as p:
        # Playwright's bundled Chromium won't start on this machine - it needs a VC++
        # runtime that isn't installed, and fails with "side-by-side configuration is
        # incorrect". The system browsers are already there and render identically for
        # our purposes, so drive one of those instead of asking for an admin install.
        browser = _launch_system_browser(
            p, args=["--force-device-scale-factor=1", "--hide-scrollbars"]
        )
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(stage),
            record_video_size={"width": W, "height": H},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)
        page.add_style_tag(content=REDACT_CSS)
        # Kill caret blink and any entry animation so the first frames are already settled.
        page.add_style_tag(content="*{caret-color:transparent!important}")
        time.sleep(settle)
        plan(page)
        time.sleep(0.8)
        ctx.close()
        browser.close()

    webm = next(stage.glob("*.webm"))
    mp4 = OUT / f"{name}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(webm),
            "-vf", f"fps=30,scale={W}:{H}:flags=lanczos,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-an", str(mp4),
        ],
        check=True,
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(mp4)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"  {name:22} {float(dur):5.1f}s  -> {mp4.relative_to(ROOT)}")
    return mp4


# --- the seven inserts --------------------------------------------------------


def c1_guards(page):
    """Hold on the docstring, then travel down to the comparison line and rest there.

    Travel distances are measured from the rendered content rather than hard-coded, so
    editing guards.py cannot silently scroll the shot past the line it is meant to land on.
    """
    span = page.evaluate(
        """() => {
             const s = document.querySelector('#scroll');
             const v = s.parentElement;
             const hl = s.querySelector('.hl');
             const end = Math.max(0, s.scrollHeight - v.clientHeight);
             // Land the highlighted line a little above centre, where the eye expects it.
             const want = hl ? hl.offsetTop - v.clientHeight * 0.42 : end;
             return [Math.min(end, Math.max(0, want)), end];
           }"""
    )
    target = int(span[0])
    time.sleep(2.5)
    smooth_scroll(page, "#scroll", target // 2, 3400)
    time.sleep(1.0)
    smooth_scroll(page, "#scroll", target, 3400)
    time.sleep(3.5)


def c2_off_rulebook(page):
    time.sleep(8.0)


def c3_activity_feed(page):
    """Find the cycle where the live model and both shadows disagree, and sit on it.

    The script wants a real disagreement on screen, not a representative-looking one, so
    this scrolls to whichever row actually contains one rather than a fixed offset.
    """
    page.evaluate(
        """() => {
             const rows = [...document.querySelectorAll('*')].filter(
               e => e.children.length === 0 && /shadows/.test(e.textContent||''));
             const hit = rows.find(e => {
               const t = e.textContent;
               const m = t.match(/chose ([a-z ]+?) · shadows (.+)/);
               if (!m) return false;
               const live = m[1].trim();
               return m[2].split(',').every(s => {
                 const v = s.split(':')[1];
                 return v && v.trim() !== live;
               });
             });
             (hit || rows[0])?.scrollIntoView({block:'center'});
             if (hit) {
               // Walk up only as far as the row, never to the feed container - closest('div')
               // grabbed the whole list last time and lit up twenty rows instead of one.
               let box = hit;
               for (let i = 0; i < 4 && box.parentElement; i++) {
                 const p = box.parentElement;
                 if (p.getBoundingClientRect().height > 90) break;
                 box = p;
               }
               box.style.transition = 'background .6s, box-shadow .6s';
               box.style.background = 'rgba(90,200,250,.20)';
               box.style.boxShadow = 'inset 3px 0 0 #0a84ff';
               box.style.outline = '1px solid rgba(10,132,255,.45)';
             }
           }"""
    )
    # Hold on the highlighted row. Nothing else moves here - the whole point of the shot is
    # that one line, so any camera move would pull the eye off it.
    time.sleep(6.5)


def c3_feed_scroll(page):
    """Slow travel down the activity feed - the 'counted, in a log anyone can open' shot."""
    top = page.evaluate(
        """() => {
             const h = [...document.querySelectorAll('*')].find(
               e => /Agent activity/i.test(e.textContent||'') && e.children.length < 6);
             return h ? h.getBoundingClientRect().top + window.scrollY - 80 : 900;
           }"""
    )
    page.evaluate("y => window.scrollTo(0, y)", top)
    time.sleep(2.0)
    smooth_scroll(page, "window", int(top) + 1400, 11000)
    time.sleep(1.5)


def c6_killswitch(page):
    """The four trading modes, revealed one at a time so each gets read."""
    page.evaluate(
        """() => {
             document.querySelectorAll('.mode').forEach((m, i) => {
               m.style.opacity = '0';
               m.style.transform = 'translateY(14px)';
               m.style.transition = 'opacity .5s ease, transform .5s ease';
               setTimeout(() => { m.style.opacity = '1'; m.style.transform = 'none'; },
                          400 + i * 900);
             });
             const f = document.querySelector('.foot');
             if (f) {
               f.style.opacity = '0';
               f.style.transition = 'opacity .6s ease';
               setTimeout(() => { f.style.opacity = '1'; }, 4400);
             }
           }"""
    )
    time.sleep(10.0)


def c7_close(page):
    """The read-only dashboard from the top - what plays under the closing VO."""
    time.sleep(3.0)
    smooth_scroll(page, "window", 1200, 9000)
    time.sleep(2.0)
    smooth_scroll(page, "window", 0, 3500)
    time.sleep(1.5)


CAPTURES = [
    ("c1_guards",        f"{PAGES}/c1_guards.html",       c1_guards),
    ("c2_off_rulebook",  f"{PAGES}/c2_off_rulebook.html", c2_off_rulebook),
    ("c3_activity_feed", DASH,                            c3_feed_scroll),
    ("c3b_disagreement", DASH,                            c3_activity_feed),
    ("c4_mleg",          f"{PAGES}/c4_mleg.html",         c2_off_rulebook),
    ("c5_doctor",        f"{PAGES}/c5_doctor.html",       c2_off_rulebook),
    # /admin is gated behind ADMIN_PASSWORD and 503s on a local build, so the four modes
    # are rendered from the same MODES definition the admin form is built from.
    ("c6_killswitch",    f"{PAGES}/c6_killswitch.html",   c6_killswitch),
    ("c7_close",         DASH,                            c7_close),
]


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("recording inserts:")
    for name, url, plan in CAPTURES:
        try:
            record(name, url, plan)
        except Exception as exc:  # keep going; one bad insert shouldn't sink the batch
            print(f"  {name:22} FAILED: {type(exc).__name__}: {exc}")
    shutil.rmtree(RAW, ignore_errors=True)
