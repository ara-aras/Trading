Real numbers below — all from the code, not idealised.

---

## Z-score (the statistical idea underneath AZTE)

A z-score answers: **"is this unusual, measured in the data's own units?"**

Take SPY's last 20 daily returns. Compute their average and their spread (standard deviation). Then:

```
z = (today's return − average) / spread
```

- `z = 0` → dead average
- `z = 1` → one standard deviation out, happens often
- `z = 2` → roughly the outer 5%, genuinely notable
- `z = −0.65` → **what SPY actually read on our last cycle. Boring.**

The point is that it's *self-scaling*. A 1% move is enormous for a bond ETF and a Tuesday for a meme stock. A z-score adapts automatically because it divides by that instrument's own recent volatility.

**One subtlety we got right on purpose:** the baseline excludes the day being scored. Include it and the reading drags toward zero — a milder version of the exact bug that pinned IV Rank at 100. [`azte.py`](src/signals/azte.py) uses `returns[:-1]` as the baseline.

## AZTE event trigger

**A**daptive **Z**-score **T**rigger **E**ngine, from the AgenticAITA paper. Idea: don't reason on a clock, reason when something *happened*. Threshold `|z| ≥ 2.0` over a 20-day window.

Most agents wake every 15 minutes and burn four model calls whether the market did anything or not. AZTE says: only think hard on high-information events.

**We compute it and log it, but deliberately don't let it gate.** Enforcing it would suppress cycles, and suppressed cycles are missing benchmark data points — we only have ~26 market hours left. So the log records what it *would* have suppressed, which is the honest way to evaluate a gate before trusting it. Flipping it on later is a config change.

---

## Quant signal vector

The only thing the AI is allowed to see. Four measured numbers plus context:

| Field | Meaning |
|---|---|
| `classifier_p_up` | LightGBM's calibrated probability the underlying closes up. **0.4069** last cycle |
| `iv_rank` | How expensive options are vs. recent history, 0–100 |
| `iv_percentile` | % of past readings below today's |
| `vrp` | Implied vol minus realised vol — are options over- or under-priced |
| `decision_time` / `data_cutoff` | Proof no future data entered |

The discipline: **the model never sees raw prices, charts, or news.** It reasons over a handful of named, pre-computed scalars. That shrinks the surface for hallucination — you can't fabricate a trend from a number you were handed.

---

## The four guards

TradeTrap's taxonomy: an LLM trading agent has four attack surfaces, each needing its own defence. **None of these calls a model** — a guard that asked an LLM whether the LLM was lying would defeat itself.

### Guard 1 · Signal validation — *before any model runs*
Checks the vector is sane: `p_up` in [0,1], `iv_rank` in [0,100], no NaN, rank and percentile not wildly disagreeing (>60 points apart).

**Ranges and NaN block. Consistency only warns.** A model handed an impossible number doesn't object — it invents a justification for it.

Live proof it works: it flags `"iv_rank is exactly 100.0 — check the ranking window is not degenerate"`. That's this morning's bug, now caught automatically.

### Guard 2 · Faithfulness — *did it make up its inputs?*
Reads the model's own reasoning text, extracts every number it quotes next to a named signal, and compares against what it was actually given. 2% tolerance so "IV rank 86.7" for 86.69 passes, but 42.0 fails hard.

Covers four signals: `classifier_p_up`, `iv_rank`, `iv_percentile`, `vrp`. **This one blocks the trade.**

A model quoting a figure it was never given has fabricated its own input — the conclusion is unsupported even when the strategy happens to be right.

### Guard 3 · Cross-validation — *is the live model an outlier?*
Four models, identical inputs. Records how many agree. Doesn't block — unanimity isn't proof, they share a rulebook and can be wrong together. But a **lone dissenting live model** is the first visible sign of one drifting.

Last cycle: not unanimous — Claude said `cash`, the live model said `bear_put_spread`.

### Guard 4 · Reconciliation — *does the broker agree we exist?*
Right before submission, re-reads positions and equity **through the CLI while the orchestrator uses the SDK** — deliberately a second, independent path. Blocks on unknown positions or >1% equity drift.

Reading the same client the agent already trusts proves nothing. Two paths disagreeing is the entire signal.

This is the one I found running on *zero* deployed cycles today — it sat inside the live-only branch. It's read-only, so it now runs in both modes.

---

## Circuit breaker

Trips after **3 consecutive execution failures** and stays tripped until a human resets it.

Different failure from the drawdown halt: that bounds losses from *bad trades*, this bounds damage from a *broken execution path* — a retry loop hammering the broker.

Two details that matter:
- **Persisted to disk.** It was in-memory, and the agent runs as a fresh process every 15 minutes, so it reset before it could ever fire. Now in `logs/agent_state.json`.
- **A success clears the counter but not the latch.** Otherwise an outage becomes an oscillation: fail, fail, fail, trip, succeed once, resume, fail again.

---

## Deterministic rulebook

The heart of the design. Every `(iv_rank, p_up)` pair maps to **exactly one** strategy:

| Condition | Strategy |
|---|---|
| `iv_rank ≥ 65` **and** neutral (0.44–0.56) | `iron_condor` |
| `p_up ≥ 0.56` | `bull_call_spread` |
| `p_up ≤ 0.44` | `bear_put_spread` |
| neutral **and** `iv_rank < 65` | `cash` |

**The model may return that strategy, or `cash`. Nothing else survives.** Python re-derives the mandate *from the raw signals* — not from the model's summary — and rejects anything different.

So "the LLM cannot manufacture a trade" is a property enforced in code, not a hope about prompt compliance. Discretion to decline, never to substitute.

It's also **exhaustive**, which the prose version wasn't: elevated IV plus a directional signal matched no clause at all, dumping 42 of 115 cycles into cash by accident.

---

## Risk gate

Plain Python, ~90 lines, no model anywhere. Runs in order:

1. **Rulebook match** — off-book strategy dies here
2. **Premium-selling halt** — no new `iron_condor` at `iv_rank ≥ 90`
3. **Daily drawdown halt** — 5%
4. **Diversification cap** — 3 concurrent underlyings
5. **Kelly sizing** — quarter-Kelly off the *calibrated classifier probability*
6. **Hard caps** — 2% per trade, 10% total open risk

The load-bearing rule: **sizing uses the classifier's probability, never the model's `confidence_score`.** An LLM saying "92% confident" is a feeling, not a calibrated probability. Feeding it into Kelly is precisely the math-hallucination this gate exists to prevent — so that number is logged for display and never touched.

Last cycle's output: `approved: 10 contracts, risking $1,965 (1.96% of equity, Kelly-sized)`.

---

The shape of the whole thing: **the AI picks between four pre-approved options or abstains. Everything that decides how much money moves is arithmetic you can read.**