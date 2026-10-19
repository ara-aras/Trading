# Brightline video edit

Builds the rough cut in DaVinci Resolve as a real, trimmable timeline. Nothing here
flattens the edit — `Trade/Outputs/*.mp4` are previews, the deliverable is the timeline.

## Pipeline

Run in this order. Each stage reads the one before it, and `edl.py` is the single source of
truth for every cut point, caption fix and section duration.

```bash
python scripts/video/fix_audio.py             # align + level audio (runs prep_footage itself)
python scripts/video/gen_sfx.py               # synthesise bleep / whoosh / sting / pop
python scripts/video/censor_bloopers.py       # bleep swearing, write Trade/BloopersCensored
python scripts/video/build_chapters.py        # render the 8 chapter cards
python scripts/video/build_transitions.py     # render the transitions as clips
python scripts/video/build_capture_pages.py   # HTML for the code / log / terminal inserts
python scripts/video/record_captures.py       # film those + the live dashboard, headless
python scripts/video/build_vo_sections.py     # retime each insert to its scripted length
python scripts/video/build_overlays.py        # captions, VO guide, graphics -> alpha movs
python scripts/video/build_resolve_timeline.py
python scripts/video/apply_grade.py           # must run AFTER the timeline is built
python scripts/video/render_preview.py        # optional
```

`build_resolve_timeline.py` recreates the timeline from scratch, which discards the grade,
so `apply_grade.py` always runs after it.

## Footage was conformed first

The six source clips are 24, 30, 120 and one variable-rate 29.08 fps. Resolve drifts audio
sync on the variable one, so everything was conformed to CFR 1080p30 in `Trade/Conformed/`.
Nothing downstream should read `Trade/ProperFootage/` — those are the untouched originals.

## Things that cost time here

**`mediaType: 1` in `clip_infos` means video ONLY.** It is the difference between a cut
with sound and a silent one, and nothing warns you — the picture is identical either way.
Omit it so each clip's linked audio comes along. `build_resolve_timeline.py` now counts the
audio items and says so.

**Whisper's timestamps are relative to the first audio sample, not to picture.** The phone
starts video first and audio ~0.4s later, recorded as a container start-time offset on four
of the six clips; extracting to WAV drops it. So every word timing needs `audio_offset()`
added back before it can be used against the video — otherwise captions run 11-14 frames
early. `fix_audio.py` bakes the same offset into the audio as real leading silence.

**Resolve's Python binding needs `PYTHONHOME`.** Without it, `import DaVinciResolveScript`
fails with `SystemError: initialization of fusionscript failed without raising an exception`,
which looks like a Python version mismatch or a disabled preference and is neither.
`resolve_env.py` sets it to `sys.prefix`. Symptom of the same root cause: `fuscript -l py3`
reports `Language 'py3' is not available`. The Lua binding (`fuscript -l lua`) works
regardless, and is a useful way to check whether Resolve itself is reachable.

**`recordFrame` is absolute, not timeline-relative.** The timeline starts at 01:00:00:00 —
frame 108000 at 30 fps. Passing `recordFrame: 0` puts a clip a full hour before the footage,
where it silently never appears; the append still returns success and the readback still
shows the right frame count. Use `timeline.GetStartFrame()`.

**`endFrame` in `clip_infos` is exclusive.** Duration is `endFrame - startFrame`. Passing
`end - 1` made all 15 clips exactly one frame short.

**ASS paints higher layers last.** A caption on layer 0 with its scrim on layer 1 renders
*underneath* its own backing. Text needs the higher layer.

**ASS alpha is inverted** relative to what you'd guess: `00` is opaque, `FF` transparent.

**Playwright's bundled Chromium doesn't run on this machine** — it needs a VC++ runtime
that isn't installed and dies with "side-by-side configuration is incorrect".
`record_captures.py` launches the system Chrome or Edge instead.

**Resolve crashes if you delete and re-import a large media pool in one breath.** It took
the application down twice. The pool had also been accumulating duplicates - 75 clips, 25
copies of the footage bin - because ImportMedia happily re-imports a path the pool already
holds. `build_resolve_timeline.py` now clears its own bins and saves between the delete and
the import.

**Never regenerate media Resolve currently has imported.** Overwriting an open .mov leaves
the clip Media Offline in the timeline. Rebuild media first, then rebuild the timeline -
which re-imports and relinks everything - rather than the other way round.

**Two Resolve MCP servers were evaluated** (`samuelgursky/davinci-resolve-mcp`,
`barckley75/resolve-claude-mcp`). Both wrap the same Python scripting API these scripts call
directly, so neither adds a capability; the second independently confirms there are no
transition or keyframe tools. It was still worth reading — it surfaced the Studio Neural
Engine calls (`Stabilize`, `SmartReframe`, `CreateMagicMask`), which are on `TimelineItem`
and are now used.

**Resolve has no transition or keyframe API.** `TimelineItem` exposes only `GetProperty` /
`SetProperty` with static values. Transitions and any animated transform have to be baked
upstream — see the Transitions section.

**`/admin` is gated behind `ADMIN_PASSWORD`** and 503s on a local build, so the four trading
modes are rendered from the `MODES` definition in `dashboard/src/app/admin/page.tsx`.

## Bloopers

Eight outtakes, 51s, after the end card and a dip to black — so a judge who only wants the
pitch can stop at 4:45. They are deliberately left ungraded: no vignette, no shot matching.
The raw look is the signal that these are offcuts. Hard cuts between them too — a dissolve
between two fluffed takes makes them feel apologetic.

`PXL_20260903_073847745` is excluded. It was shot in portrait (pillarboxes to black bars)
and its audio is unintelligible — the multilingual Whisper model guesses Japanese on what is
4.8s of mumbling.

### Bleeping

`censor_bloopers.py` finds profanity in the word-level transcripts, mutes each span and lays
a 1 kHz tone over it, and masks the same word in the caption. Both halves have to agree —
bleeping the audio while the caption spells the word out is a common and slightly absurd
failure.

The bleep is baked into the clip's audio rather than placed as a timeline item: an item can
be nudged, muted or deleted by accident, and censoring should not be able to come apart.

**It currently finds nothing.** The word list covers English and common Hindi/Urdu profanity,
but Whisper's English model does not reliably transcribe swearing and mangles non-English
entirely. If there is swearing in these takes, add the clip and timestamp to
`MANUAL_BLEEPS` — the machinery is wired and one run re-bakes it.

## Sound effects

All synthesised in `gen_sfx.py` from ffmpeg's own oscillators and noise sources, so nothing
carries a licence. A sound effect pulled off a search result carries whatever terms the
uploader attached — usually unknown, occasionally "all rights reserved" — and nobody checks
until it is a problem. A censor bleep is a 1 kHz sine anyway.

Cues are placed on their own audio track (A2, named "sfx") anchored to a plan item by name,
so they can be muted or moved without touching dialogue. Note that `GetClipProperty("Frames")`
returns 0 for an audio-only file — length has to come from the file, or the append silently
does nothing.

## Chapter cards, and why the dissolves went

Frame-stepping the first cut of the transitions showed the problem plainly: a cross-dissolve
between two talking-head shots in different locations puts **both faces on screen at once**
for the length of the blend. Prateek and Rafan were ghosted over each other for most of a
second. That is not a curve that needs easing, it is the wrong transition for the material.

Worth recording what did *not* work, because it seemed reasonable at the time: replacing the
linear crossfade with a smoothstep one made it worse. Easing concentrates the actual change
in the middle of the transition, so it reads as a snap. The standard film dissolve is linear
for exactly that reason.

What replaced it: section joins now dip to black, hold a card naming what is coming, and dip
back up. Eight of them, same editorial system as the full-screen graphic. It reads as
deliberate, it gives a judge a beat to re-orient, and there is no ghosting because only one
image is ever on screen.

A dissolve now survives in exactly three places, all of them joins where both sides are the
same scene and framing: the mic-cut in the bottle scene, and the two insert-to-insert joins.

## Transitions

Resolve's scripting API cannot add one. There is no `AddTransition`, and `SetProperty`
writes static values with no keyframes, so a dissolve cannot be faked with overlapping
clips and opacity either. `build_transitions.py` renders each as its own short clip and
`plan()` places it between the two shots, trimming both neighbours by its length exactly as
a dissolve does. They are ordinary timeline items — delete one, or swap it for a Resolve
transition by hand. The trade-off is that they are baked rather than adjustable in place.

Types are chosen per join in `TRANSITIONS` (`edl.py`): dissolves within a scene, dip to
black across a real scene change, a horizontal blur in and out of the screen inserts. The
join from the bottle collapse into `PoisonedMarket2` is deliberately absent — that clip
opens on the floor and whip-pans up to Prateek, so the footage already carries it.

## Motion graphics

`Trade/Graphics/videos/brightline-overlays/` is a HyperFrames project (CLI pinned to
0.8.27). It renders the five-step pipeline strip — SIGNALS → MODEL → RULEBOOK → RISK GATE →
BROKER — that the script asks for in section 2, plus the four strategy cards stamped
MAX LOSS: KNOWN. Output is ProRes 4444 with alpha, placed on V5 over `2 one cycle`.

```bash
cd Trade/Graphics/videos/brightline-overlays
npx hyperframes check .
npx hyperframes render . --format mov -o ./renders/pipeline.mov
```

Two things to know. The skill states macOS/Linux prerequisites but runs on Windows — it
ships its own `chrome-headless-shell`, which works here even though Playwright's Chromium
does not. And `:nth-of-type` in a composition counts by element type, not class: every
child in the strip is a `div`, so the connector selectors matched the step boxes until they
were given explicit ids.

## Overlays

Three separate alpha movs so any one can be swapped or switched off:

| track | file | notes |
|---|---|---|
| V5 | `pipeline.mov` | HyperFrames motion graphics, anchored to one section |
| V4 | `graphics.mov` | title card, UNVERIFIED / REJECTED stamps, end card |
| V3 | `vo_guide.mov`  | script lines still to be dubbed — **delete once VO is recorded** |
| V2 | `captions.mov`  | word-by-word captions for on-camera audio |

QuickTime RLE, not ProRes 4444: at 1080p30 ProRes 4444 runs ~330 Mbit/s, about 12 GB for a
five-minute overlay that is mostly empty frames. RLE is lossless and compresses
transparency to nearly nothing.

## Captions

Generated from Whisper `medium.en` word timestamps. Corrections live in `CAPTION_FIXES` in
`edl.py`. The rule applied: fix what Whisper misheard, never "improve" how anyone spoke —
captions have to match the audio, so grammar quirks stay in.

Where a correction changes the word count, the corrected words are spread evenly across the
segment instead of inheriting per-word timings that no longer line up.

## Audio

`fix_audio.py` writes `Trade/Synced/`, which is what the timeline actually uses — the raw
`Trade/Conformed/` files are its input, not the edit's source. It is a separate directory
because Resolve holds imported files open and replacing them in place fails mid-run.

Levels as shot ranged from -12 to -32 LUFS, a 20 dB step between adjacent shots. Two-pass
`loudnorm` brings everything to -16 LUFS (`LUFS_TARGET` in `edl.py`), true peak -1.5 dBTP.

Verify sync after any change by cross-correlating the render against each source clip
rather than trusting it; the last measured worst-case drift was 0.6 frames.

## Cinematic pass

Four things, each chosen because it was measured rather than assumed.

**Stabilisation.** `apply_grade.py` runs Studio's `TimelineItem.Stabilize()` on PrateekIntro
and RafanIntro only. Frame-to-frame motion measures 3.8-5.8 on those against 1.6-1.9 for the
locked-off lab shots. PoisonedMarket2 measures highest of all at 10.6 — that is the whip pan
up off the floor, so it is deliberately excluded; stabilising it would fight the shot.

**Filmic split.** Warm highlights via CDL slope, cool shadows via CDL offset. Values are
small: the footage already carries a warm cast, so more red turns skin orange. The cool
shadow lift does most of the work and partly counterweights that cast.

**Vignette and grain**, baked in `prep_footage.py` — CDL cannot express either, and there is
no keyframe or effect API to reach for. Footage only; a vignette over a dashboard screenshot
looks like a mistake.

**Self-calibrating exposure match.** The target is the median of the clips themselves,
computed at run time, not a fixed number. Shot matching is about shots agreeing with each
other. It also has to be, now: the measurement is centre-cropped (the vignette drags a
whole-frame mean down, and matching on that washes the vignette back out), and a fixed
target broke the moment that crop was introduced — three clips pinned at the gamma clamp.

**Not done: letterbox.** It is the most recognisably cinematic move and the wrong one here.
Heads sit high in frame — in the menu scene hair is at y≈20 — so 2.39:1 bars would cut
foreheads. Say the word and it goes in as a deletable overlay track.

## Picture repairs

`prep_footage.py` handles per-clip fixes that a grade cannot: the menu scene's laptop crop,
and the cold open's over-sharpening. PrateekIntro was shot with the phone's sharpening hard
on — at 1:1 there are bright halos on every leaf edge and the skin texture is crunched.
That is baked into the pixels, so it gets `hqdn3d` plus a *negative* `unsharp`, which
softens rather than sharpens. Flagged per clip via `repair=` in `edl.py`.

## Grade

`apply_grade.py` applies ASC CDL per timeline item, correcting only two measured problems:
the bottle sketch cutting from Y 112 to Y 148 between adjacent shots, and flat saturation
(5–12 on signalstats). It deliberately does not touch the warm cast — Cr sits above neutral
on all six clips by a similar amount, so that is the phone's white balance rather than a
mismatch, and pulling red out of it makes everyone look ill.

Corrections are applied at 70% strength; matching two shots exactly flattens whichever was
better lit. Adjust `TARGET_Y`, `STRENGTH` and `SATURATION`, or clear the CDL per clip on the
Color page.
