"""The voiceover lines still to be recorded, written to be said rather than read.

Three rules applied to every line here:

  * Sized to its gap at about 130 words per minute, not 150. That is a comfortable speaking
    pace with room to breathe, rather than a race against the picture - and these are being
    read aloud by people who are presenting, not narrating for a living.

  * No jargon a judge would have to decode. No "signal vector", no "defined-risk", no
    "isotonic calibration". Where a term has to appear at all - m-leg - it is explained in
    the very next breath.

  * Short sentences. Every full stop is somewhere to take a breath, and somewhere to pick
    the take up again if it goes wrong, instead of restarting the whole paragraph.

Say them your way if a phrase does not sit right. The claims are what matter, not the
wording - every one of these is something the repo can actually back up.

These also drive the on-screen guide text burned into vo_guide.mov, so the words on screen
during recording are the words below.
"""

from __future__ import annotations

# Keyed by section name in edl.CUTS. Line breaks are where to breathe.
VO_LINES: dict[str, str] = {
    "3 guards insert":
        "We don't ask another AI if the first one lied.\n"
        "That would be the same problem twice.\n"
        "We just check the numbers.",

    "5 alpaca mleg":
        "Every order goes through Alpaca's command line tool.\n"
        "It's built for bots that run on a schedule.\n"
        "The command is plain text, so we keep the exact one\n"
        "that reached the broker.\n"
        "See m-leg. That means multi leg.\n"
        "Both halves of the trade fill together, or neither does.\n"
        "You can never be left holding half a trade.",

    "5 alpaca doctor":
        "Before it builds an order, it checks it is pointed\n"
        "at a paper account. If that fails, the job stops.\n"
        "It can never find out afterwards that it was\n"
        "trading real money.\n"
        "The size comes from our own maths.\n"
        "Never more than two percent. We never ask the AI.",

    "6 benchmark":
        "Every cycle, three AIs get the same numbers.\n"
        "Only one is allowed to trade.\n"
        "The other two are marked, and never touch the account.\n"
        "Look here. The live one says do nothing.\n"
        "The other two want to bet the market drops.",

    "6 benchmark feed":
        "Because our rulebook is just a calculation,\n"
        "we can mark all three right or wrong the same day.\n"
        "We don't have to wait and see who made money.\n"
        "Across the week they tried to break the rules\n"
        "on six to twenty five percent of cycles.\n"
        "Not one got through.\n"
        "It's all counted, in a log anyone can open.",

    "9 close":
        "Five days of profit and loss is mostly luck.\n"
        "For us, and for everyone else here.\n"
        "Anyone who says they have proven a strategy in a week\n"
        "is selling you something.\n"
        "Here is what we can show you.\n"
        "Every no came from a rule with a name.\n"
        "No AI ever decided how much money moved.\n"
        "And every time we got something wrong,\n"
        "our own log said so first.",
}
