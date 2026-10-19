"""The cut list, the caption corrections, and the timings everything else derives from.

Single source of truth. record_captures.py, build_vo_sections.py and build_resolve_timeline.py
all read this, so a change to a cut point here propagates rather than needing three edits.

Times are seconds in the CONFORMED clips (Trade/Conformed/), which are all 1080p30 CFR.
The originals are mixed - 24, 30, 120 and one variable-rate 29.08 - and Resolve drifts audio
sync on the variable one, so nothing downstream should ever touch Trade/ProperFootage/.
"""

from __future__ import annotations

import functools
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FPS = 30

_ROOT = Path(__file__).resolve().parents[2]

# Loudness target for the finished mix. -16 LUFS is the usual figure for web video, and the
# takes range from -12 to -32 as shot, which is a 20 dB jump between adjacent shots.
LUFS_TARGET = -16.0


@functools.lru_cache(maxsize=None)
def audio_offset(stem: str) -> float:
    """Seconds by which this clip's audio starts AFTER its video.

    The phone starts capturing video first and the audio pipeline joins ~0.4s later, so four
    of the six clips carry a container-level offset. It matters twice:

      * the audio has to be delayed by this much to stay in sync with the picture, and
      * Whisper's timestamps are relative to the first audio SAMPLE, because extracting to
        WAV drops the offset - so every word timing needs it added back before it can be
        used against the video.

    Read from the untouched original rather than stored, so it cannot drift out of date.
    """
    src = _ROOT / "Trade" / "ProperFootage" / f"{stem}.mp4"
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=start_time", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        return max(0.0, float(out))
    except ValueError:
        return 0.0


# Where each clip's audio sits relative to its picture, in seconds. NEGATIVE means the
# audio is pulled EARLIER than the container would place it.
#
# These were shot with a Bluetooth headset as the microphone and the camera does not
# compensate for the link's latency, so the sound lands late by an amount that varies per
# take - the headset re-pairs between takes. None of it appears in the container metadata:
# KillSwitch reports an 18 ms audio start offset and needed 400 ms of correction.
#
# measure_sync.py produced a first estimate by correlating mouth movement against audio
# energy. These are the values Rafan then CONFIRMED BY EAR against build_sync_test.py, which
# is the only check that actually settles it - the correlation is a proxy and it was wrong
# by 150-300 ms on four of the six clips, and by 315 ms on KillSwitch.
#
# The number here is the FINAL offset applied to the audio, not a correction on top of the
# container's own value. Change one of these and re-run fix_audio.py, then rebuild.
CONFIRMED_SHIFT: dict[str, float] = {
    "PrateekIntro":   -0.150,   # "C is closer but still slightly fast"
    "RafanIntro":     -0.204,   # A
    "PoisonedMarket": -0.170,   # A
    "PoisonedMarket2": -0.140,  # A
    "Waiter":         -0.245,   # A
    "KillSwitch":     -0.400,   # "bring it to around -400ms"
}


def audio_shift(stem: str) -> float:
    """Total seconds to move this clip's audio relative to picture.

    Both the audio conform and the caption timings must use this same number, or the
    captions drift away from the words the moment the sync is corrected.
    """
    if stem in CONFIRMED_SHIFT:
        return CONFIRMED_SHIFT[stem]
    # Anything not yet checked by ear falls back to the container's own offset.
    return audio_offset(stem)


@dataclass
class Cut:
    """One clip on the timeline. `src` is a stem in Trade/Conformed or Trade/Captures."""

    section: str
    src: str
    start: float
    end: float
    kind: str = "footage"          # footage | insert | vo | blooper
    crop_bottom: int = 0           # source pixels trimmed off the bottom, then rescaled
    vo_text: str = ""              # burned-in temp guide text for sections Rafan dubs later
    repair: str = ""               # "" | "sharpening" - see prep_footage.py
    note: str = ""

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    @property
    def start_frame(self) -> int:
        return int(round(self.start * FPS))

    @property
    def end_frame(self) -> int:
        """Exclusive, matching Resolve's clip_info convention."""
        return int(round(self.end * FPS))


# --- the standard cut ---------------------------------------------------------
# Section 8 (thermometer) is dropped, per the script's own recommendation and Rafan's
# instruction. Section 7 keeps the brake beat but not the steering-wheel beat: the
# steering wheel was never shot, and KillSwitch.mp4 replaces it with the neck pull.

CUTS: list[Cut] = [
    # 1 - COLD OPEN. Prateek delivers the first half of the intro; the script assigns these
    # lines to Rafan but they were shot the other way round, which works better anyway -
    # the project gets introduced by someone before the person who narrates it.
    Cut("1 cold open", "PrateekIntro", 14.80, 38.40, repair="sharpening",
        note="first 15s of the source is dead air / setup - dropped; heavy phone sharpening"),

    # 1b/2 - Rafan picks up the same sentence and runs straight into the cycle walkthrough.
    Cut("2 one cycle", "RafanIntro", 3.20, 31.60,
        note="covers script section 2 end to end, incl. the spread explanation"),

    # 3 - THE POISONED BOTTLE.
    #
    # The dead section is 7.20-9.20, where Rafan holds the bottle up and talks to the crew
    # about clipping a mic to his collar. The camera is repositioned during it - the framing
    # visibly changes between 9.2 and 9.3 - so the join is covered by a short dissolve.
    #
    # Everything from 9.20 to the end of the clip is the performance and runs uncut: the
    # line, the drink, the reaction, the collapse out of frame, and the empty frame after it.
    Cut("3 bottle", "PoisonedMarket", 1.20, 7.20,
        note="masked man offers the bottle; Rafan's first line"),
    Cut("3 bottle poisoned", "PoisonedMarket", 9.20, 22.766,
        note="line, drink, reaction, collapse, empty frame - plays through, no internal cut"),

    # Opens on Rafan twitching on the floor and whip-pans up to Prateek. That pan is an
    # in-camera transition, so it starts at 0.0 and no transition is added over the join.
    Cut("3 bottle explain", "PoisonedMarket2", 0.00, 18.10,
        note="floor twitch -> whip pan -> Prateek explains the guards"),

    # The one beat in section 3 nobody said out loud.
    Cut("3 guards insert", "c1_guards", 0.0, 12.0, kind="vo",
        vo_text="And notice — we don't ask a second AI whether the first one lied.\n"
                "That's just the same problem twice. It's arithmetic.",
        note="~24 words @150wpm"),

    # 4 - THE ONE-ITEM MENU. Phone was resting on a laptop; the keyboard and its reflection
    # sit in the bottom ~95px of frame. Measured at y=985, stable for the whole take.
    Cut("4 menu", "Waiter", 0.30, 29.20, crop_bottom=112,
        note="crop removes laptop keyboard/touchpad reflection, then rescale to 1080"),

    Cut("4 rulebook insert", "c2_off_rulebook", 0.0, 8.0, kind="insert",
        note="real off-rulebook verdict: model chose iron_condor, rulebook mandated cash"),

    # 5 - HOW IT TALKS TO ALPACA. Not shot. 129 words @150wpm = ~52s, split across the two
    # pieces of evidence the section cites.
    Cut("5 alpaca mleg", "c4_mleg", 0.0, 28.0, kind="vo",
        vo_text="Every order goes through Alpaca's own command-line tool, built for bots\n"
                "running on a schedule. The exact command that hit the broker is text,\n"
                "so it goes in our log. See mleg — multi-leg. Both sides fill together\n"
                "or neither does. You can't end up holding half a trade.",
        note="script section 5, first half"),

    Cut("5 alpaca doctor", "c5_doctor", 0.0, 24.0, kind="vo",
        vo_text="Before it builds any order, it checks it's pointed at a paper account.\n"
                "If that fails, the job stops. Size comes from our own model, never more\n"
                "than two percent. We never ask the AI how confident it feels.",
        note="script section 5, second half"),

    # 6 - THE BENCHMARK. 122 words @150wpm = ~49s.
    Cut("6 benchmark", "c3b_disagreement", 0.0, 20.0, kind="vo",
        vo_text="Every cycle, three different AIs get the same numbers. One is allowed to\n"
                "trade. The other two get marked and never touch the account.\n"
                "There — the live one says do nothing. The other two want to bet the\n"
                "market drops. Same numbers, three answers.",
        note="framed on a real disagreement: groq cash, both shadows bear put spread"),

    Cut("6 benchmark feed", "c3_activity_feed", 0.0, 29.0, kind="vo",
        vo_text="Because our rulebook is just a calculation, we can mark all three right or\n"
                "wrong the same day. Across the week they tried to break the rules on six\n"
                "to twenty-five percent of cycles. Not one got through.\n"
                "Counted, in a log anyone can open.",
        note="script section 6, second half"),

    # 7 - BRAKE. Steering-wheel beat cut (never shot); neck pull replaces it.
    Cut("7 brake", "KillSwitch", 0.10, 15.50,
        note="plays from the top: Rafan working, Prateek walks in at 0.7s, grabs his neck "
             "at 2.7s, Rafan slumps at 4.0s, then Prateek explains over him. The old cut "
             "started at 4.60 and threw the whole gag away, keeping only the explanation"),

    Cut("7 killswitch modes", "c6_killswitch", 0.0, 10.0, kind="insert",
        note="/admin - the four trading modes, the only control anyone has"),

    # 9 - CLOSE. 83 words @150wpm = ~33s.
    Cut("9 close", "c7_close", 0.0, 33.0, kind="vo",
        vo_text="Five days of profit and loss is mostly luck. For us and for everyone here.\n"
                "What we can show you: every 'no' came from a rule with a name. No AI ever\n"
                "decided how much money moved. Three of them marked against the same\n"
                "standard, every cycle, in the open.",
        note="script section 9"),

    # --- BLOOPERS -------------------------------------------------------------
    # Runs after the end card, so a judge who only wants the pitch can stop there.
    #
    # Full takes, not trimmed. The point of an outtake is what happens around the fluff, and
    # trimming to the punchline threw away the reactions either side of it.
    #
    # Hard cuts between these, no transitions. Bloopers want snap; a dissolve between two
    # fluffed takes just makes them feel apologetic.

    Cut("b1 prateek intro", "PXL_20260903_065042375", 0.00, 25.42, kind="blooper",
        note="full take - Prateek's intro, lands on 'or forget about them'"),
    Cut("b2 barefoot spread", "PXL_20260903_074023194", 0.00, 11.43, kind="blooper",
        note="full take - 'Barefoot spread' instead of bear put spread"),
    Cut("b4 everything to me", "PXL_20260903_071529912", 0.00, 7.93, kind="blooper",
        note="full take - 'you mean everything to me'"),
    Cut("b5 risk guard", "PXL_20260903_072744528", 0.00, 12.43, kind="blooper",
        note="full take - explanation trails off mid-sentence"),
    Cut("b6 great day", "PXL_20260903_075853516", 0.00, 11.61, kind="blooper",
        note="full take - 'whenever there is a great day, great day to you'"),
    Cut("b7 short take", "PXL_20260903_073847745", 0.00, 4.83, kind="blooper",
        note="full take - landscape; audio is unintelligible, kept for the reaction"),
    Cut("b8 thank you", "PXL_20260903_071457153", 0.00, 2.07, kind="blooper",
        note="full take - the right note to end on"),
]


# --- fit the VO sections to the recorded takes --------------------------------
from vo_audio import LEAD, TAIL, VO_AUDIO, vo_duration  # noqa: E402


def _fit_vo_sections() -> None:
    """Resize each voiceover section to its actual take.

    Must run after TRANSITIONS exists: a transition eats time off both ends of the item it
    touches, so the cut has to be long enough to carry the lead, the take, the tail AND
    whatever the two transitions take away.
    """
    for i, cut in enumerate(CUTS):
        stem = VO_AUDIO.get(cut.section)
        if cut.kind != "vo" or not stem:
            continue
        spoken = vo_duration(stem)
        if spoken <= 0:
            continue
        prev_t = TRANSITIONS.get(CUTS[i - 1].section, ("", 0.0))[1] if i else 0.0
        next_t = TRANSITIONS.get(cut.section, ("", 0.0))[1]
        cut.end = cut.start + prev_t + LEAD + spoken + TAIL + next_t



# --- caption corrections ------------------------------------------------------
# Rule applied here: fix what Whisper misheard, never 'improve' how anyone actually spoke.
# Grammar quirks stay in - they are what was said, and the captions have to match the audio.
# Entries are (clip stem, wrong text, right text).

CAPTION_FIXES: list[tuple[str, str, str]] = [
    # Proper noun, mangled identically in both places it appears.
    ("PrateekIntro", "Brightlight", "Brightline"),

    # UNVERIFIED - flagged to Rafan. Script says "one cycle, across four funds" and the
    # dashboard confirms four underlyings (DIA/IWM/QQQ/SPY), so "4 cycles / 4 parts" is
    # almost certainly a mishear - but it could also be a genuine slip on the day.
    ("RafanIntro", "the system runs on 4 cycles, going across 4 parts",
     "the system runs one cycle, going across four funds"),

    # "RISTGARD" is not a thing; the module is src/guards.py.
    ("PoisonedMarket2", "We introduce RISTGARD, which basically checks",
     "We introduce our guards, which basically check"),

    ("KillSwitch", "That's the kill stage.", "That's the kill switch."),

    # The menu scene is the worst-transcribed take - it is shot at a distance with two
    # voices overlapping. Every one of these is a domain term Whisper had no chance on.
    ("Waiter", "Where for the bread, sir? What if I want mine? No.",
     "Bear put spread, sir. — What if I want an iron condor? — No."),
    ("Waiter", "What if I want it? No.", "What if I'm really confident? — No."),
    ("Waiter", "So, can I have it? Yes, you can always have it there.",
     "So, can I have nothing? — Yes, you can always have nothing."),
    ("Waiter", "And that's our rule. The numbers go in only once a day, sir.",
     "And that's our rulebook. The numbers go in, and exactly one trade comes out."),
    ("Waiter", "The air can take it and say no, but it cannot do anything else.",
     "The AI can take it, or say no — but it cannot pick anything else."),
    ("Waiter", "So, we calculate that rate rather than the original numbers.",
     "So we work the allowed trade out again ourselves, from the original numbers."),
    ("Waiter", "If it doesn't match, please reject it.",
     "If it doesn't match, it's thrown out."),

    ("PoisonedMarket", "Hey bro, anybody ever said a lot, but the market is up 50%",
     "Hey bro — NVIDIA posted a loss, but their market's up 50%!"),
    ("PoisonedMarket", "Oh, is it? But isn't there a stock plug, anyways that's fine, I'll just take it",
     "Oh, is it? But isn't that a stock loss… anyway that's fine, I'll just take it."),
]

# Corrections above that are inferred from the script rather than clearly audible.
# Rafan should spot-check these two against the take before anything is burned in.
NEEDS_VERIFY = [
    ("RafanIntro", "runs on 4 cycles, going across 4 parts"),
    ("PoisonedMarket", "anybody ever said a lot"),
]



# The spoken lines live in their own module - see vo_lines.py for why they are
# worded the way they are. Applied here so a Cut carries its own guide text.
from vo_lines import VO_LINES  # noqa: E402

for _cut in CUTS:
    if _cut.section in VO_LINES:
        _cut.vo_text = VO_LINES[_cut.section]

# --- chapter cards ------------------------------------------------------------
# Inserted between sections, with a dip to black either side.
#
# They exist because a cross-dissolve between two talking-head shots in different locations
# ghosts both faces over each other for the whole blend - frame-stepping the old join shows
# Prateek and Rafan superimposed for most of a second. Easing the curve does not help; the
# problem is that both images are on screen at once. Cutting to a named card instead reads
# as deliberate, and gives a judge a beat to re-orient.
#
# `dur` is the whole card. The fades are the fadeblack transitions either side, which eat
# 0.7s from each end, leaving about 1.2s of clean card.

CHAPTERS: list[dict] = [
    {"src": "ch01_cycle", "before": "2 one cycle", "dur": 2.6,
     "title": "One cycle,<br/>end to end", "right": "Section 01",
     "sub": "Every fifteen minutes, across four funds - and the same five steps every time."},
    {"src": "ch02_guards", "before": "3 bottle", "dur": 2.6,
     "title": "The guards", "right": "Section 02",
     "sub": "What happens when you let a language model tell you what the numbers were."},
    {"src": "ch03_rulebook", "before": "4 menu", "dur": 2.6,
     "title": "The rulebook", "right": "Section 03",
     "sub": "The numbers go in. Exactly one trade comes out as allowed."},
    {"src": "ch04_market", "before": "5 alpaca mleg", "dur": 2.6,
     "title": "Reaching<br/>the market", "right": "Section 04",
     "sub": "Every order is a line of text, and every line of text is in the log."},
    {"src": "ch05_models", "before": "6 benchmark", "dur": 2.6,
     "title": "Three models,<br/>one standard", "right": "Section 05",
     "sub": "Same numbers, three answers, all three marked the same day."},
    {"src": "ch06_killswitch", "before": "7 brake", "dur": 2.6,
     "title": "The kill switch", "right": "Section 06",
     "sub": "One button stops everything. No button chooses anything."},
    {"src": "ch07_show", "before": "9 close", "dur": 2.6,
     "title": "What we<br/>can show", "right": "Section 07",
     "sub": "Five days of profit and loss proves nothing. Here is what does."},
    {"src": "ch08_bloopers", "before": "b1 prateek intro", "dur": 2.6, "num": False,
     "title": "Bloopers", "right": "And the takes that did not work",
     "sub": "It took rather more attempts than the film suggests."},
]


def _insert_chapters() -> None:
    """Splice a chapter Cut in front of each named section."""
    by_before = {c["before"]: c for c in CHAPTERS}
    out: list[Cut] = []
    for cut in CUTS:
        ch = by_before.get(cut.section)
        if ch:
            out.append(Cut(f"= {ch['src']}", ch["src"], 0.0, ch["dur"], kind="chapter",
                           note=f"chapter card: {ch['title']}"))
        out.append(cut)
    CUTS[:] = out


_insert_chapters()


# --- transitions --------------------------------------------------------------
# Resolve's scripting API exposes no way to add a transition - there is no AddTransition,
# and SetProperty writes static values with no keyframes - so each transition is rendered
# as its own short clip and placed between the two shots. It behaves exactly like a
# dissolve (it consumes `dur` from the outgoing tail and the incoming head) and it stays a
# separate, deletable timeline item; the trade-off is that it is baked rather than
# adjustable as a Resolve transition object.
#
# Keyed by the section the transition FOLLOWS. A section with no entry gets a straight cut.

# "smoothfade" is not an ffmpeg transition name - build_transitions.py maps it to xfade's
# custom expression with a smoothstep curve. A plain crossfade ramps linearly, which is what
# makes a short dissolve read as cheap: it spends the whole time at a visible half-and-half
# double exposure. Easing in and out puts most of the duration near the two ends instead.
#
# Durations are roughly doubled from the first pass - 0.4s was too quick to read as a
# deliberate transition and just looked like a glitch.
TRANSITIONS: dict[str, tuple[str, float]] = {
    # A dissolve is only used where BOTH sides are the same scene and framing. Between two
    # different shots it superimposes two faces, which is what made the previous cut feel
    # like a mistake. Everything else dips through black - either side of a chapter card,
    # or on its own where a section has no card.
    #
    # Linear, not eased. Easing a dissolve concentrates the actual change in the middle,
    # which reads as a snap rather than a blend; the standard film dissolve is linear for
    # exactly that reason.

    "1 cold open":        ("fadeblack", 0.70),
    "= ch01_cycle":       ("fadeblack", 0.70),
    "2 one cycle":        ("fadeblack", 0.70),
    "= ch02_guards":      ("fadeblack", 0.70),

    # Same shot, same framing - this is the join left behind by cutting the mic-placement
    # chatter, and a dissolve is exactly right for hiding the camera reposition.
    "3 bottle":           ("fade",      0.80),
    # "3 bottle poisoned" is absent on purpose: PoisonedMarket2 opens on the floor and
    # whip-pans up to Prateek. The footage already carries the transition.
    "3 bottle explain":   ("fadeblack", 0.50),
    "3 guards insert":    ("fadeblack", 0.70),
    "= ch03_rulebook":    ("fadeblack", 0.70),

    "4 menu":             ("fadeblack", 0.50),
    "4 rulebook insert":  ("fadeblack", 0.70),
    "= ch04_market":      ("fadeblack", 0.70),

    # Two dark text screens - nothing to ghost, so a dissolve is safe here.
    "5 alpaca mleg":      ("fade",      0.60),
    "5 alpaca doctor":    ("fadeblack", 0.70),
    "= ch05_models":      ("fadeblack", 0.70),

    # Same dashboard, same framing.
    "6 benchmark":        ("fade",      0.60),
    "6 benchmark feed":   ("fadeblack", 0.70),
    "= ch06_killswitch":  ("fadeblack", 0.70),

    "7 brake":            ("fadeblack", 0.50),
    "7 killswitch modes": ("fadeblack", 0.70),
    "= ch07_show":        ("fadeblack", 0.70),

    "9 close":            ("fadeblack", 0.70),
    "= ch08_bloopers":    ("fadeblack", 0.70),
}


# Runs here, after TRANSITIONS exists - the fit depends on how much the transitions
# either side take off the section.
_fit_vo_sections()


@dataclass
class PlanItem:
    """One item as it will actually sit on the timeline."""

    name: str
    kind: str            # footage | insert | vo | transition
    src: str             # stem, resolved to a directory by the caller
    start: float         # in-point in the source
    end: float           # out-point in the source
    tl_start: float      # where it begins on the timeline
    cut: "Cut | None" = None

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    @property
    def start_frame(self) -> int:
        return int(round(self.start * FPS))

    @property
    def end_frame(self) -> int:
        return int(round(self.end * FPS))

    @property
    def frames(self) -> int:
        """Length in frames, derived from the in/out points.

        Not round(duration * FPS): that rounds a different quantity and can disagree by a
        frame - 27.15s reads as 814 that way, while frames 112..927 is 815, and Resolve
        builds from the in/out points.
        """
        return self.end_frame - self.start_frame


def plan() -> list[PlanItem]:
    """The cut list with transitions folded in, and every timeline position resolved.

    A transition of length T shortens the outgoing shot's tail and the incoming shot's head
    by T each, then occupies T itself - so the pair loses T of runtime, exactly as a
    dissolve does in any NLE.
    """
    items: list[PlanItem] = []
    t = 0.0
    for i, cut in enumerate(CUTS):
        prev_t = TRANSITIONS.get(CUTS[i - 1].section, ("", 0.0))[1] if i else 0.0
        next_t = TRANSITIONS.get(cut.section, ("", 0.0))[1]

        head, tail = cut.start + prev_t, cut.end - next_t
        if tail - head < 0.5:
            raise ValueError(
                f"{cut.section}: transitions ({prev_t}s + {next_t}s) leave "
                f"{tail - head:.2f}s of clip - shorten them"
            )

        items.append(PlanItem(cut.section, cut.kind, cut.src, head, tail, t, cut))
        t += round(tail - head, 3)

        if next_t:
            kind = TRANSITIONS[cut.section][0]
            name = f"t{i:02d}_{kind}"
            items.append(PlanItem(f"-> {cut.section}", "transition", name,
                                  0.0, next_t, t))
            t += next_t
    return items


def source_path(item) -> Path:
    """Where a plan item's (or cut's) media actually lives.

    Every footage clip goes through prep_footage now - all of them get the vignette and
    grain pass - so Prepared is the source of truth for picture. Synced is only its input,
    and reading from it would silently drop the treatment.
    """
    trade = _ROOT / "Trade"
    kind = getattr(item, "kind", "footage")
    if kind == "transition":
        return trade / "Transitions" / f"{item.src}.mp4"
    if kind == "chapter":
        return trade / "Chapters" / f"{item.src}.mp4"
    if kind == "blooper":
        # Censored, not merely conformed: the bleeps are baked into the audio.
        return trade / "BloopersCensored" / f"{item.src}.mp4"
    if kind not in ("footage",):
        return trade / "VOSections" / f"{item.src}.mp4"
    cut = getattr(item, "cut", None) or item
    return trade / "Prepared" / f"{cut.src}.mp4"


def transcript_dir(kind: str) -> Path:
    return _ROOT / "Trade" / ("BloopersTranscripts" if kind == "blooper" else "Transcripts")


def total_runtime() -> float:
    return round(sum(i.duration for i in plan()), 2)


if __name__ == "__main__":
    print(f"{'section':22} {'source':20} {'in':>7} {'out':>7} {'dur':>7}  kind")
    print("-" * 78)
    t = 0.0
    for c in CUTS:
        print(f"{c.section:22} {c.src:20} {c.start:7.2f} {c.end:7.2f} "
              f"{c.duration:7.2f}  {c.kind}")
        t += c.duration
    m, s = divmod(t, 60)
    print("-" * 78)
    print(f"{'TOTAL':22} {'':20} {'':7} {'':7} {t:7.2f}  = {int(m)}:{s:04.1f}")
    foot = sum(c.duration for c in CUTS if c.kind == "footage")
    print(f"\n  on-camera footage : {foot:6.1f}s")
    print(f"  needs your VO     : {sum(c.duration for c in CUTS if c.kind == 'vo'):6.1f}s")
    print(f"  silent inserts    : {sum(c.duration for c in CUTS if c.kind == 'insert'):6.1f}s")
