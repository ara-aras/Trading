# Brightline - voiceover script

Six pieces to record. **295 words**, about **2 minutes 15** of speaking.
Everything else in the film is already on camera.

## How to record these

- **The pace is already worked out.** Each block is sized to its gap at about 130 words
  a minute, which is unhurried. Don't rush to fill the time - there is slack in every one.
- **Each line break is a breath.** They are also safe places to stop and pick the take
  back up, so one fluff never costs you the whole paragraph.
- **Say it your way.** If a phrase doesn't sit right in your mouth, change it. The claim
  is what matters, not the wording - every one of these is something the repo backs up.
- **Same mic, same room, all six.** Mismatched voiceover is more obvious than a
  mismatched shot. The headset is fine, just don't switch halfway.
- **Record each block as its own file**, named by the heading.

### Two to say carefully

- **m-leg** - say it as *"em-leg"*. The next line explains it, so a judge who has never
  heard the term still follows.
- **"Every no came from a rule with a name"** - lean on *no*. That is the whole argument
  of the film in six words.

---

## 3 guards insert

`1:26.67 - 1:36.97`  ·  **10.3s**  ·  22 words  ·  128 wpm

*You'll be looking at:* guards.py, scrolling down to the line that compares what the model said against what it was actually given.

```
We don't ask another AI if the first one lied.
That would be the same problem twice.
We just check the numbers.
```

## 5 alpaca mleg

`2:13.07 - 2:39.37`  ·  **26.3s**  ·  57 words  ·  130 wpm

*You'll be looking at:* the real order command from the log, with --order-class mleg highlighted.

```
Every order goes through Alpaca's command line tool.
It's built for bots that run on a schedule.
The command is plain text, so we keep the exact one
that reached the broker.
See m-leg. That means multi leg.
Both halves of the trade fill together, or neither does.
You can never be left holding half a trade.
```

## 5 alpaca doctor

`2:40.27 - 3:02.47`  ·  **22.2s**  ·  49 words  ·  132 wpm

*You'll be looking at:* live `alpaca doctor` output, resolving to paper-api.alpaca.markets.

```
Before it builds an order, it checks it is pointed
at a paper account. If that fails, the job stops.
It can never find out afterwards that it was
trading real money.
The size comes from our own maths.
Never more than two percent. We never ask the AI.
```

## 6 benchmark

`3:03.37 - 3:21.62`  ·  **18.2s**  ·  41 words  ·  135 wpm

*You'll be looking at:* the activity feed, held on a real cycle where the live model chose cash and both shadows chose bear put spread.

```
Every cycle, three AIs get the same numbers.
Only one is allowed to trade.
The other two are marked, and never touch the account.
Look here. The live one says do nothing.
The other two want to bet the market drops.
```

## 6 benchmark feed

`3:22.47 - 3:49.52`  ·  **27.1s**  ·  58 words  ·  129 wpm

*You'll be looking at:* the activity feed scrolling.

```
Because our rulebook is just a calculation,
we can mark all three right or wrong the same day.
We don't have to wait and see who made money.
Across the week they tried to break the rules
on six to twenty five percent of cycles.
Not one got through.
It's all counted, in a log anyone can open.
```

## 9 close

`4:08.67 - 4:39.37`  ·  **30.7s**  ·  68 words  ·  133 wpm

*You'll be looking at:* the dashboard from the top, then the end card.

```
Five days of profit and loss is mostly luck.
For us, and for everyone else here.
Anyone who says they have proven a strategy in a week
is selling you something.
Here is what we can show you.
Every no came from a rule with a name.
No AI ever decided how much money moved.
And every time we got something wrong,
our own log said so first.
```

---

Once they're recorded: drop them on A3 in Resolve, delete the **vo guide** track (V3),
and tell me - I'll re-time the gaps to your actual takes and regenerate the captions
so they cover the voiceover too.
