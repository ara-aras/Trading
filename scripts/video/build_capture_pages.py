"""Generate the static HTML pages that the screen-capture recorder films.

Every page here renders real project data - guards.py as it is on disk, an audit record
lifted verbatim from logs/audit_log.jsonl, the actual command that hit the broker, real
`alpaca doctor` output. Nothing is mocked, which is the rule the video script sets for
itself: a judge who opens the repo after watching has to find the same thing.

All of it is set in the same editorial system as the chapter cards and the full-screen
motion graphics: paper ground, ink and cobalt, heavy Helvetica against small tracked
uppercase, hairline rules, hard offset shadows. These pages used to be dark, which meant
the film alternated between two unrelated design languages every time it cut to a screen.
Being real evidence is a reason for the CONTENT to be untouched; it was never a reason for
the styling to be different.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Trade" / "CapturePages"
AUDIT = ROOT / "logs" / "audit_log.jsonl"

SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  :root {{
    --paper:#f2f0ea; --ink:#10161f; --accent:#0a4fd3;
    --rule:#c9c4b8; --panel:#ffffff;
  }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; padding:0; background:var(--paper); color:var(--ink);
    font-family:Helvetica,Arial,sans-serif;
    width:1920px; height:1080px; overflow:hidden; }}
  .frame {{ padding:74px 92px; height:1080px; display:flex; flex-direction:column; }}
  .label {{ font-family:Consolas,monospace;
    font-size:17px; letter-spacing:.30em; text-transform:uppercase;
    opacity:.55; }}
  .path {{ font-family:"Arial Black",Helvetica,sans-serif;
    font-size:52px; letter-spacing:-.02em; margin-top:14px; color:var(--ink); }}
  .path b {{ color:var(--accent); font-weight:inherit; }}
  .hr {{ height:3px; background:var(--ink); margin:22px 0 26px; }}
  .viewport {{ flex:1; overflow:hidden; position:relative;
    background:var(--panel); border-left:9px solid var(--accent);
    box-shadow:14px 14px 0 rgba(16,22,31,.09); padding:30px 34px; }}
  /* Travelled with a transform, not scrollTop - an absolutely positioned child of an
     overflow:hidden parent has no scrollport, so scrollTop silently does nothing. */
  .scroller {{ position:absolute; top:30px; left:34px; right:34px; will-change:transform; }}
  /* Code keeps hard newlines - wrapping it destroys the indentation that makes it
     readable. Pages showing long single-line data opt into wrapping themselves. */
  pre {{ margin:0; font-family:Consolas,monospace;
    font-size:19px; line-height:1.66; white-space:pre; color:var(--ink); }}
  .hl {{ background:rgba(10,79,211,.10); box-shadow:inset 4px 0 0 var(--accent);
    display:block; margin:0 -34px; padding:0 30px; }}
  .fade {{ position:absolute; left:0; right:0; height:90px; pointer-events:none; }}
  .fade.top {{ top:0; background:linear-gradient(var(--panel),transparent); }}
  .fade.bot {{ bottom:0; background:linear-gradient(transparent,var(--panel)); }}
  {extra}
</style></head><body><div class="frame">{body}</div></body></html>
"""


def write(name: str, title: str, body: str, extra: str = "") -> Path:
    p = OUT / f"{name}.html"
    p.write_text(SHELL.format(title=title, body=body, extra=extra), encoding="utf-8")
    return p


def head(label: str, path_html: str) -> str:
    return (f'<div class="label">{label}</div>'
            f'<div class="path">{path_html}</div><div class="hr"></div>')


def page_guards() -> None:
    """guards.py, scrolled to check_faithfulness, with the comparison line marked.

    Highlighting the f-string is the point: it is the line that literally compares what the
    model said against what the model was handed, which is the claim the bottle sketch makes.
    """
    src = (ROOT / "src" / "guards.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    # Anchor on content, not a line number - guards.py is still being edited.
    target = next(
        i for i, l in enumerate(lines) if "reasoning cites" in l and "was given" in l
    )
    start, end = 110, min(len(lines), target + 12)
    excerpt = "\n".join(lines[start:end])

    # A light Pygments theme, to match the paper ground.
    fmt = HtmlFormatter(nowrap=True, style="xcode")
    code = highlight(excerpt, PythonLexer(), fmt)
    out = []
    for i, row in enumerate(code.split("\n")):
        n = start + i + 1
        cls = ' class="hl"' if n == target + 1 else ""
        out.append(f"<span{cls}>{row}</span>")

    body = (
        head("Fabrication guard",
             "src/guards.py &middot; <b>check_faithfulness()</b>")
        + '<div class="viewport"><div class="scroller" id="scroll">'
        + f'<pre>{chr(10).join(out)}</pre>'
        + '</div><div class="fade top"></div><div class="fade bot"></div></div>'
    )
    write("c1_guards", "guards.py", body, extra=fmt.get_style_defs(".frame"))


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _find_record(pred) -> dict | None:
    with AUDIT.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if pred(rec):
                return rec
    return None


def page_off_rulebook() -> None:
    """One real off-rulebook verdict: model wanted a trade, the rulebook mandated cash."""
    rec = _find_record(
        lambda r: any(
            d.get("compliant") is False and d.get("rulebook_mandated")
            for d in _walk(r) if isinstance(d, dict)
        )
    )
    if rec is None:
        raise SystemExit("no off-rulebook record found in audit_log.jsonl")

    verdict = next(
        d for d in _walk(rec)
        if isinstance(d, dict) and d.get("compliant") is False and d.get("rulebook_mandated")
    )
    rows = []
    for line in json.dumps(verdict, indent=2).splitlines():
        hot = any(k in line for k in ('"selected"', '"rulebook_mandated"', '"compliant"'))
        esc = html.escape(line)
        rows.append(f'<span class="hl">{esc}</span>' if hot else f"<span>{esc}</span>")

    body = (
        head("Audit record &middot; rulebook verdict", "logs/<b>audit_log.jsonl</b>")
        + f'<div class="viewport"><pre>{chr(10).join(rows)}</pre></div>'
    )
    write("c2_off_rulebook", "off-rulebook", body,
          extra="pre {white-space:pre-wrap; word-break:break-word; font-size:22px;}")


def page_mleg() -> None:
    """The exact multi-leg order string that reached Alpaca, straight out of the log."""
    cmd = None
    with AUDIT.open(encoding="utf-8") as fh:
        for line in fh:
            m = re.search(r"alpaca order submit [^\"]+", line)
            if m:
                cmd = m.group(0).replace('\\"', '"').replace("\\\\", "\\")
                break
    if cmd is None:
        raise SystemExit("no `alpaca order submit` command found in audit_log.jsonl")

    esc = html.escape(cmd).replace(
        "--order-class mleg", '<b class="mark">--order-class mleg</b>')
    body = (
        head("The command that hit the broker",
             "logs/audit_log.jsonl &middot; <b>order.command</b>")
        + f'<div class="viewport"><pre><span class="prompt">$</span> {esc}</pre></div>'
    )
    write("c4_mleg", "mleg order", body, extra="""
      pre {font-size:23px; white-space:pre-wrap; word-break:break-all; line-height:1.6;}
      .prompt {color:var(--accent); font-weight:700;}
      .mark {background:rgba(10,79,211,.13); color:var(--accent);
        padding:2px 7px; font-weight:700;}
    """)


def page_doctor() -> None:
    """Live `alpaca doctor`, proving the account it is pointed at is the paper one."""
    res = subprocess.run(["alpaca", "doctor"], capture_output=True, text=True, timeout=60)
    out = res.stdout or res.stderr
    # Belt and braces: the script forbids any key material on screen, and doctor is not
    # supposed to print any. Redact anything key-shaped before it can reach a frame.
    out = re.sub(r"\b(PK|AK)[A-Z0-9]{10,}\b", "█" * 20, out)

    rows = []
    for line in out.splitlines():
        esc = html.escape(line).replace("✓", '<span class="ok">✓</span>')
        if "paper-api.alpaca.markets" in line:
            esc = esc.replace("https://paper-api.alpaca.markets",
                              '<b class="mark">https://paper-api.alpaca.markets</b>')
            rows.append(f'<span class="hl">{esc}</span>')
        else:
            rows.append(f"<span>{esc}</span>")

    body = (
        head("It checks the account before it builds an order", "$ <b>alpaca doctor</b>")
        + f'<div class="viewport"><pre>{chr(10).join(rows)}</pre></div>'
    )
    write("c5_doctor", "alpaca doctor", body, extra="""
      pre {font-size:21px;}
      .ok {color:#0a7a3d; font-weight:700;}
      .mark {background:rgba(10,79,211,.13); color:var(--accent);
        padding:2px 7px; font-weight:700;}
    """)


def page_modes() -> None:
    """The four trading modes, read out of the admin page's own MODES definition.

    The live /admin route is gated behind ADMIN_PASSWORD and returns 503 on a local build,
    and it renders as a form with dropdowns - which reads poorly at video size anyway. The
    definition below is the same data the form is built from.
    """
    src = (ROOT / "dashboard" / "src" / "app" / "admin" / "page.tsx").read_text(
        encoding="utf-8")
    block = re.search(r"const MODES = \[(.*?)\n\];", src, re.S)
    if not block:
        raise SystemExit("could not find MODES in admin/page.tsx")
    modes = re.findall(
        r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*detail:\s*"([^"]+)"',
        block.group(1))
    if len(modes) != 4:
        raise SystemExit(f"expected 4 modes, parsed {len(modes)}")

    cards = "".join(
        f'<div class="mode"><div class="mv">{html.escape(v)}</div>'
        f'<div class="ml">{html.escape(l)}</div>'
        f'<div class="md">{html.escape(d)}</div></div>'
        for v, l, d in modes)

    body = (
        head("The only control anyone has over the agent",
             "Four modes. <b>None of them pick a trade.</b>")
        + f'<div class="cards">{cards}</div>'
        + '<div class="foot">One button stops everything '
          '&mdash; no button chooses anything</div>'
    )
    write("c6_killswitch", "trading modes", body, extra="""
      .cards {margin-top:6px; display:grid; grid-template-columns:1fr 1fr; gap:30px;
        align-content:start;}
      .mode {background:var(--panel); border-left:9px solid var(--accent);
        padding:30px 34px 28px; box-shadow:14px 14px 0 rgba(16,22,31,.09); opacity:0;}
      .mv {font-family:Consolas,monospace; font-size:14px; letter-spacing:.24em;
        text-transform:uppercase; opacity:.5;}
      .ml {font-size:38px; font-weight:800; margin:9px 0 12px; letter-spacing:-.01em;}
      .md {font-size:21px; line-height:1.5; opacity:.7;}
      .foot {margin-top:auto; padding-top:30px; font-family:Consolas,monospace;
        font-size:18px; letter-spacing:.14em; text-transform:uppercase;
        color:var(--accent);}
    """)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    page_guards()
    page_off_rulebook()
    page_mleg()
    page_doctor()
    page_modes()
    for p in sorted(OUT.glob("*.html")):
        print(f"{p.name:24} {p.stat().st_size:>7,} bytes")
