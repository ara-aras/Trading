"""Render the two stills the write-up uses, straight from the live record.

Both are generated rather than hand-grabbed so they can be re-cut after any run: one is a
crop of the running dashboard, the other is a small page built from `logs/audit_log.jsonl`
so the risk gate's own verdicts -- including the refusals -- are readable at a glance.

Needs the dashboard served at http://localhost:3000 (`npm --prefix dashboard run start`).
"""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
AUDIT = ROOT / "logs" / "audit_log.jsonl"
DASH = "http://localhost:3000"


def _launch(p, **kw):
    """Prefer an installed Chrome/Edge; the bundled Chromium refuses to spawn on this box."""
    for channel in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=channel, **kw)
        except Exception:
            continue
    return p.chromium.launch(**kw)


def shoot_live_vs_shadow(page) -> None:
    """Crop the newest row of per-underlying cards: one block per model, reasoning intact."""
    page.goto(DASH, wait_until="networkidle")
    page.wait_for_timeout(2500)
    section = page.locator("section").filter(
        has=page.get_by_role("heading", name="Live vs. shadow")
    ).first
    box = section.bounding_box()
    height = page.evaluate(
        """(top) => {
          const sec = [...document.querySelectorAll('section')].find(
            s => s.querySelector('h2') && s.querySelector('h2').textContent.includes('Live vs'));
          const grid = sec.querySelector('div.grid') || sec.children[1];
          const rects = [...grid.children].map(k => k.getBoundingClientRect());
          const rowTop = Math.min(...rects.map(r => r.top));
          const firstRow = rects.filter(r => Math.abs(r.top - rowTop) < 10);
          return Math.max(...firstRow.map(r => r.bottom)) + window.scrollY - top;
        }""",
        box["y"] - 8,
    )
    page.screenshot(
        path=str(OUT / "dashboard-live-vs-shadow.png"),
        full_page=True,
        clip={
            "x": box["x"] - 8,
            "y": box["y"] - 8,
            "width": box["width"] + 16,
            "height": height + 12,
        },
    )


def _gate_cycles(underlying: str = "DIA") -> list[dict]:
    """Every distinct refusal reason, plus the first two approvals, in time order.

    One card per reason rather than per cycle: the log repeats `already holding` dozens of
    times, and the point of the still is the set of ways the gate can say no.
    """
    cycles = [
        d
        for line in AUDIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for d in [json.loads(line)]
        if d.get("underlying") == underlying and d.get("risk_gate_verdict")
    ]

    picked: list[dict] = []
    seen: set[str] = set()
    approvals = 0
    for d in cycles:
        verdict = d["risk_gate_verdict"]
        if verdict["approved"]:
            if approvals < 2:
                approvals += 1
                picked.append(d)
            continue
        reason = verdict["reason"].split("(")[0].strip()
        if reason not in seen:
            seen.add(reason)
            picked.append(d)
    picked.sort(key=lambda d: d["timestamp"])
    return picked


def _gate_page(underlying: str = "DIA") -> str:
    def esc(value) -> str:
        return html.escape(str(value))

    cards = []
    for d in _gate_cycles(underlying):
        verdict, decision, signals = d["risk_gate_verdict"], d["live_decision"], d["signals"]
        approved = verdict["approved"]
        pill = (
            '<span class="pill ok">&#10003; approved</span>'
            if approved
            else '<span class="pill no">&#10007; rejected</span>'
        )
        fill = d.get("fill_result") or {}
        broker = ""
        if fill.get("submitted"):
            order_id = fill.get("response", {}).get("id", "")
            broker = (
                '<div class="cmd"><div class="lbl">broker call &middot; atomic multi-leg,'
                " one order id</div>"
                f'<pre>{esc(fill["command"])}</pre>'
                f'<div class="meta">exit {fill.get("exit_code")} &middot; '
                f'{esc(fill.get("endpoint", ""))} &middot; order {esc(order_id)}</div></div>'
            )
        state = "ok" if approved else "no"
        stamp = d["timestamp"][:19].replace("T", " ")
        cards.append(
            f"""
    <article class="card {state}">
      <header><span class="sym">{esc(underlying)}</span>
        <span class="ts">{esc(stamp)} UTC</span></header>
      <div class="sig">
        <div><span class="k">price</span><span class="v">${signals['current_price']:.2f}</span></div>
        <div><span class="k">p(up)</span><span class="v">{signals['classifier_p_up']:.4f}</span></div>
        <div><span class="k">equity</span><span class="v">${d['account_equity']:,.2f}</span></div>
        <div><span class="k">model pick</span>
          <span class="v">{esc(decision['selected_strategy'])}</span></div>
      </div>
      <div class="verdict">
        <div class="row"><span class="lbl">risk gate</span>{pill}</div>
        <p class="reason">{esc(verdict['reason'])}</p>
        <div class="row"><span class="lbl">contracts</span>
          <span class="v">{verdict['contracts']}</span></div>
      </div>
      {broker}
    </article>"""
        )

    style = """
:root{--bg:#FBFAF7;--ink:#141414;--mut:#6B6660;--line:#E4E0D8;--red:#C0392B;--redbg:#FBEDEB;
      --grn:#1F6F45;--grnbg:#EAF3ED;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);width:1180px;padding:34px 38px;
     font:15px/1.55 -apple-system,Segoe UI,Inter,sans-serif}
h1{font-size:21px;margin:0 0 4px;letter-spacing:-.01em}
h1 .bar{display:inline-block;width:4px;height:17px;background:#B08A48;margin-right:9px;
        vertical-align:-2px;border-radius:2px}
.sub{color:var(--mut);font-size:13.5px;margin:0 0 22px}
.card{border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:12px;
      background:#fff}
.card.no{background:#FEFCFB}
header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:11px}
.sym{font-weight:640;letter-spacing:.01em}
.ts{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--mut)}
.sig{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding-bottom:12px;
     border-bottom:1px solid var(--line)}
.sig .k,.verdict .lbl{display:block;font:11px ui-monospace,Consolas,monospace;
     text-transform:uppercase;letter-spacing:.07em;color:var(--mut)}
.sig .v,.verdict .v{font:14px ui-monospace,Consolas,monospace}
.verdict{padding-top:11px}
.verdict .row{display:flex;justify-content:space-between;align-items:center;gap:12px}
.verdict .row+.row{margin-top:9px}
.reason{margin:7px 0 0;font-size:14px;color:#2A2A2A}
.pill{font:11.5px ui-monospace,Consolas,monospace;padding:3px 9px;border-radius:999px;
      border:1px solid}
.pill.no{color:var(--red);background:var(--redbg);border-color:#F0CFC9}
.pill.ok{color:var(--grn);background:var(--grnbg);border-color:#C6DED0}
.cmd{margin-top:13px;padding-top:12px;border-top:1px solid var(--line)}
.cmd .lbl{font:11px ui-monospace,Consolas,monospace;text-transform:uppercase;
     letter-spacing:.07em;color:var(--mut)}
pre{margin:7px 0 6px;font:12px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;
    word-break:break-word;background:#F6F4EF;border:1px solid var(--line);border-radius:7px;
    padding:10px 12px}
.meta{font:11.5px ui-monospace,Consolas,monospace;color:var(--mut)}
footer{margin-top:16px;font-size:12.5px;color:var(--mut);border-top:1px solid var(--line);
       padding-top:11px}
"""
    intro = (
        "Deterministic Python, downstream of the model. The model's pick is an input here,"
        " never the last word &mdash; every verdict below is replayed from"
        " <code>logs/audit_log.jsonl</code>."
    )
    note = (
        "Sizing is Kelly-capped against account equity; the gate also enforces one position per"
        " underlying and a daily drawdown halt. Approved orders go to the broker as a single"
        " <code>mleg</code> order, so both legs fill together or neither does."
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        + style
        + "</style></head><body>\n"
        f'<h1><span class="bar"></span>Risk gate &mdash; {esc(underlying)}</h1>\n'
        f'<p class="sub">{intro}</p>\n'
        + "\n".join(cards)
        + f"\n<footer>{note}</footer>\n</body></html>"
    )


def shoot_risk_gate(page, underlying: str = "DIA") -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "gate.html"
        src.write_text(_gate_page(underlying), encoding="utf-8")
        page.goto(src.as_uri())
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / f"risk-gate-{underlying.lower()}.png"), full_page=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        shoot_live_vs_shadow(page)
        page.set_viewport_size({"width": 1180, "height": 1000})
        shoot_risk_gate(page)
        browser.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
