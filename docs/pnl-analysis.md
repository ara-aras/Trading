# Why the P&L is negative

> Written 2026-09-03, with the account at $94,418.26 (−5.58%) and the agent in its own
> drawdown halt. Nothing here was changed in response. See §7 for why.

Every figure below comes from `logs/audit_log.jsonl` (250 cycles) and 821 days of daily bars.

---

## 1. What actually happened

23 fills across five sessions. **All 23 were `bear_put_spread`.** Not a majority — all of
them. The rulebook mandated `bear_put_spread` on 148 of 244 signal-bearing cycles.

Meanwhile every underlying rose:

| | first logged | last logged | move |
|---|---|---|---|
| SPY | 769.35 | 772.94 | +0.47% |
| QQQ | 714.55 | 717.82 | +0.46% |
| IWM | 293.10 | 295.29 | +0.75% |
| DIA | 529.63 | 537.28 | +1.44% |

A modest, flat-to-slightly-up market. The agent was short it, every time, with long premium.

The obvious reading is "the classifier was wrong about direction". That reading is wrong, and
it is worth being precise about why — the real cause is fixable, and "the model was wrong" is
not.

## 2. Root cause: the classifier and the rulebook do not speak the same units

`src/signals/direction.py:56` defines the label:

```python
df["target"] = (df["fwd_return"] > FORWARD_THRESHOLD).astype(int)   # > +0.5% over 3 days
```

So **`p_up` is P(3-day return > +0.5%)**. It is *not* P(the market goes up), and `1 - p_up` is
*not* P(the market goes down).

`src/decision_schema.py:131` consumes it as though it were:

```python
if bearish:   # p_up <= 0.44
    return "bear_put_spread", ...
```

Here are the unconditional base rates of that exact label, over 821 days:

| | P(> +0.5%) | P(< −0.5%) | P(flat, within ±0.5%) |
|---|---|---|---|
| SPY | **0.449** | 0.280 | 0.270 |
| QQQ | **0.480** | 0.314 | 0.206 |
| IWM | **0.419** | 0.358 | 0.223 |
| DIA | **0.402** | 0.280 | 0.318 |

Read the SPY row against the 0.44 bear threshold. **SPY's base rate is 0.449.** A classifier
that has learned nothing at all, and simply emits the base rate, lands within a whisker of
"bearish". IWM (0.419) and DIA (0.402) sit *permanently below* the threshold — for those two
names the rulebook mandates a bearish trade by default and needs positive evidence to stop.

That is the whole mechanism. **The agent was not reading a bearish signal. It was reading the
base rate and calling it bearish.**

The second half of the error is the missing middle. `1 - p_up` bundles P(down) together with
P(flat). For DIA that is 0.280 down and **0.318 flat** — more than half of the "bearish
evidence" is the probability of a market that goes nowhere. A bear put spread bought into a
flat market loses its entire debit. The observed market was exactly that flat band.

Across 244 cycles `p_up` ranged 0.311 to 0.531 against a bull threshold of 0.56, which is why
`bull_call_spread` has never once fired. Same cause. The README logged that as a separate
limit; it is not separate. Both branches are miscalibrated by one units error.

## 3. Compounding cause: Kelly was fed the wrong probability

`src/orchestrator.py:393`:

```python
classifier_win_probability=direction.p_up,
```

One number, used as the win probability for every strategy. For `bull_call_spread` that is
approximately right. For `bear_put_spread` the trade wins when the market **falls**, so the
win probability is P(down) ≈ 0.28, not `p_up` ≈ 0.41.

Every bearish position in this account was therefore sized on the probability of the market
moving against it, and `_kelly_fraction` never returned the negative edge that would have
refused the trade outright.

## 4. Compounding cause: the aggregate caps did not exist during the drawdown

Each gate refusal reason, dated to the first time it ever fired:

| Rule | First fired |
|---|---|
| premium-selling halt | Aug 31 16:33 |
| `max_total_open_risk_pct` | Aug 31 19:46 |
| `one_position_per_underlying` | Sep 1 15:17 |
| negative-edge Kelly refusal | Sep 1 19:17 |
| `max_underlyings_concurrent` | Sep 2 16:15 |
| daily drawdown halt | Sep 3 15:30 |

Now look at Aug 30–31 on SPY: **16 consecutive fills, every cycle, not one refusal.** Six on
Aug 30, ten on Aug 31, each approved at ~1.9% of equity, "Kelly-sized".

16 × 1.9% ≈ **30% of equity committed to a single directional view**, against a stated ceiling
of `max_total_open_risk_pct: 0.10`. The per-trade cap was enforced. The aggregate cap was not
yet wired, and `one_position_per_underlying` did not exist for another day.

The bulk of the drawdown is those two sessions. The caps that would have prevented it were
each built immediately after the damage they describe — which is why they now exist, and also
means the loss was taken before the rule was written.

## 5. The counterfactual

Replace the fixed 0.44 / 0.56 thresholds with thresholds relative to **each symbol's own base
rate**, ±0.06. Nothing else changes — same classifier, same signals, same IV logic, the same
audit log replayed:

```
CURRENT rulebook:    bear_put_spread 148 · cash 45 · iron_condor 45
BASE-RATE rulebook:  cash 120 · iron_condor 95 · bear_put_spread 23
```

Bearish mandates fall by 84%. Condors more than double. Applied to the 23 trades actually
filled:

**22 of 23 would never have been placed.** The 23rd (DIA, Sep 3, IV rank 79.1) becomes an
`iron_condor` — the structure that profits from precisely the flat market that occurred.

This is a replay of recorded signals, not a backtest, and it is not evidence of edge. It is
evidence about *this specific defect*: the trades that lost the money were mandated by a
threshold comparison that was never meaningful.

## 6. What would make the agent genuinely smarter

Ranked by expected effect, root cause first.

1. **Give the label symmetric semantics.** Either train a three-class head (down / flat / up
   at ±0.5%) and let the rulebook read `P(down)` for bear branches and `P(up)` for bull, or
   drop the threshold to `fwd_return > 0` so 0.50 is genuinely neutral and the existing
   0.44 / 0.56 numbers mean what they were written to mean. Fixes §2 and §3 at once, and is
   the only change that removes the cause rather than compensating for it.

2. **Anchor thresholds to each symbol's base rate**, if the label stays as it is. Cheap,
   one-function change, effect shown in §5. Compensates for the defect rather than removing
   it, so it ranks second.

3. **Pass the correct win probability per strategy.** `p_win` for a bear structure is
   `P(down)`; for a condor it is `P(flat)`. Kelly is only as good as the probability handed
   to it, and right now three different bets are sized off one number.

4. **Refuse to re-enter on an unchanged signal.** The classifier trains on daily bars, so
   `p_up` was byte-identical across all six Aug 30 SPY fills (0.4069) and all ten Aug 31
   fills (0.4311). Sixteen entries expressed one opinion. A rule that declines to open on a
   name whose signal has not moved since the last entry costs nothing and removes the
   concentration mechanism directly.

5. **Add intraday features.** A daily model queried every 15 minutes has nothing new to say
   for 26 consecutive cycles. Either query it once per session, or give it intraday inputs
   and let it actually change its mind.

6. **Source IV rank from real vendor history.** IWM printed IV rank 0.0 at 13:46 and 24.4 at
   14:16 the same day. A rank computed from ~40 self-recorded samples is not a rank, and the
   premium branch depends on it.

## 7. What we did about it: nothing, deliberately

Every finding above was available before the measurement window closed. None of it was applied
to the running agent, for three reasons:

- **It could not have helped.** The agent hit its own daily drawdown halt at 15:30 UTC on
  Sep 3 and opened nothing afterwards. The official P&L snapshot is EOD Sep 3. There was no
  cycle left for a change to affect.
- **Changing thresholds after seeing the outcome is fitting to the outcome.** The record
  exists because the rules did not move underneath it. A base-rate threshold chosen on Aug 28
  would be a finding; the same number chosen on Sep 3, after watching it lose, is a number
  chosen to have been right.
- **The defect is the more interesting result.** An agent that logged enough about its own
  reasoning for its operators to locate a units error in the label, three layers upstream of
  the loss, is the thing worth showing. The drawdown halt firing on schedule is the second.

The P&L is bad, and it is bad for a reason we can name, prove from our own record, and show
the fix for. We would rather submit that than a number that happened to be positive.
