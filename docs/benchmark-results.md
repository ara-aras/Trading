# Shadow benchmark — results

> Scored 2026-09-03 16:36 UTC over 250 logged cycles. The market has not yet closed, so the
> final tally will shift by a handful of cycles; the rates below are stable to within a
> fraction of a percent. Reproduce with `python scripts/model_benchmark.py`.

Three models receive an identical signal vector every cycle. One executes; the others are
recorded and scored and never touch the account. Because the rulebook is a pure function of
the same signals, every answer is markable immediately — this is compliance measured today,
not profitability measured in weeks.

---

## The table

| model | answered | mandate | abstain | off-book | off-book rate | abstention |
|---|---|---|---|---|---|---|
| mistral (shadow) | 248 | 177 | 61 | 10 | **4.0%** | 25% |
| **groq (live)** | 250 | 166 | 62 | 22 | **8.8%** | 25% |
| featherless (shadow) | 235 | 199 | 2 | 34 | **14.5%** | 1% |
| claude_code_cli | 6 | 5 | 1 | 0 | — | — |
| anthropic | 0 | — | — | — | never answered | — |

`claude_code_cli` answered 6 times. That is not a sample, and it is listed rather than ranked.

Ranked by **off-book rate**, not compliance rate. Ranking on compliance would reward a model
that always proposes something and punish one that declines — the opposite of what this
system values. `featherless` is the case that makes the point: highest compliance count (199)
*and* the worst discipline, because it abstained on 2 cycles out of 235. It nearly always has
an opinion, and 34 of those opinions were not permitted.

**Models disagreed on 113 of 250 cycles (45%).** Unanimous on 136. The live model was the lone
dissenter 21 times.

## The claim this exists to test

**22 live off-book attempts. 0 reached the broker.** All 22 refused by the gate; every one of
the 23 actual fills was rulebook-compliant. Verified independently of the benchmark script by
re-reading `fill_result` against `live_rulebook` in the raw log.

## The interesting part: what the off-book attempts actually were

All 22 live off-book cycles are the same trade, and it is not a rogue one:

```
tried:    iron_condor  × 22
mandated: cash         × 22
IV rank:  73.7 – 100.0
iv_rank_trusted: False × 22
symbols:  QQQ × 20, IWM × 2
```

The model was shown a high IV rank and proposed the textbook response — sell premium. The
rulebook mandated cash **only because that IV rank was not backed by enough recorded history
to be trusted** (the gate needs 30 samples across ≥2 calendar days).

So the disagreement between the model and the rulebook was never about strategy. It was about
**provenance**. The model trusted a number; the system did not trust its own number.

The shadows split the same way — `featherless` tried `iron_condor` on 30 cycles where cash was
mandated, `mistral` on 7. Three independent models, given the same untrusted IV rank, all
reached for the same trade. That is not three models failing. That is one signal being
displayed with more authority than it had earned.

## The part that cuts against us

In a market that finished flat to slightly up (+0.47% to +1.44%, see
[`pnl-analysis.md`](pnl-analysis.md)), those iron condors would probably have made money. The
constraint that refused them cost P&L.

It was still the right refusal, and the reason is in the same log: IWM printed IV rank 0.0 at
13:46 and 24.4 at 14:16 on Sep 3. A rank computed from ~40 self-recorded samples is not a
rank. Selling premium on it would have been correct by luck, from a number that had no
business being traded on.

Both halves belong in the record. The gate held, and the rulebook it was enforcing was
miscalibrated.

## Which model actually performed better

Off-book rate measures discipline. It does not measure judgment, and the two come apart.

Judgment is scoreable here because the outcome is known: every filled `bear_put_spread` lost,
all four underlyings rose, so **abstaining from a `bear_put_spread` mandate was the correct
call**. Abstention is always permitted, so declining one costs a model nothing on the
compliance score — which makes it a clean read on whether a model will decline a bad trade it
is allowed to take.

| model | off-book rate (discipline) | declined the losing mandate (judgment) |
|---|---|---|
| **mistral** | **4.0%** | 40.4% (61 of 151) |
| groq (live) | 8.8% | **40.8%** (62 of 152) |
| featherless | 14.5% | **1.4%** (2 of 144) |

**mistral wins.** Best discipline, judgment tied with groq inside noise.

The second column also retires a charitable reading of `featherless`. Its 30 iron-condor
proposals against cash mandates look like a model seeing what the rulebook missed. They are
not. The same model accepted 142 of 144 `bear_put_spread` mandates that all lost. The condor
proposals and the losing-mandate compliance are one behaviour: it does not decline. A 1%
abstention rate is not boldness, it is the absence of a refusal.

`groq` is the only model that did both — it proposed the condors *and* posted the highest
decline rate on the mandate that was losing money.

**And the live backbone barely mattered.** 40.8% against 40.4% on the only axis that touches
P&L is noise, and off-book rate cannot move P&L at all because the gate rejects those
regardless. Agent Market Arena (arXiv:2510.11695) reports that framework variation dominates
backbone variation; with the framework pinned this hard, we measured that in our own account
rather than citing it. Swapping the live model would have changed the returns by approximately
nothing.

## What the benchmark actually establishes

- The constraint is real and it binds: 22 attempts, 0 executions, in a live account.
- Backbone choice survives hard framework constraint. Agent Market Arena (arXiv:2510.11695)
  reports that framework dominates backbone; with the framework pinned to one permitted answer
  or a refusal, the residual backbone variation is still **4.0% to 14.5%** off-book — a
  3.6× spread across models given identical inputs.
- Abstention is a behavioural signature, not noise. 25% / 25% / 1% is a stable, repeated
  difference in how willing each model is to say nothing.
- 45% disagreement across three models on the same inputs is the number that matters most for
  anyone tempted to treat a single LLM's trading opinion as a signal.
