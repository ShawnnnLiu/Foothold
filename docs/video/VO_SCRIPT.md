# Foothold Demo Video - VO Script And ElevenLabs Prompts (2026-08-11, TTS switched 2026-08-20)

Voiceover script and ElevenLabs generation prompts for the locked 2-minute narrative.
TTS switched from K2-FSA Omnivoice to ElevenLabs on 2026-08-20; the prompts below apply unchanged.
Clip layout: intro 25s (countdown-calendar), demo 1:05, outro 25s (countdown-resolution).
Total runtime target 1:55; total VO ~250 words at ~130 wpm, leaving room for the music cut and silence beat at the climax.

Disclosure: ElevenLabs (TTS voiceover generation) must be on the contest's mandatory AI tools list; K2-FSA Omnivoice was dropped before any final audio was produced with it.

## Voice Design Prompt (master)

> Female narrator, late twenties, neutral American accent, natural documentary storyteller.
> Low-to-medium pitch with a slight husk, intimate close-mic presence, minimal room tone.
> Speaks in measured phrases with real pauses, like she is telling you something that matters.
> Grounded and credible, quietly intense; never a commercial announcer, never chirpy, never salesy.
> Clean articulation of numbers and course codes; no vocal fry drag at phrase ends.

Per-segment emotion deltas (applied on top of the master design):

- INTRO: hushed urgency; low volume, slightly clipped phrasing, tension rising line over line; serious, almost confidential.
- DEMO A (walkthrough): steady confidence with forward momentum; tempo a notch faster; brightening as the wall fills.
- DEMO B (traps): sharper and pointed; controlled edge of indignation; hits the numbers hard.
- CLIMAX: slow and hushed going in; then firm, resolute, almost proud on the key line; no smile.
- OUTRO: calm, warm, relieved; the tension is gone; ends with quiet conviction, slowing on the final tagline.

## Script

Numbers in [brackets] are inline non-verbal cues for the TTS input.
Timecodes assume the intro clip starts at 0:00 with ~2s of music before the first line.

### INTRO - over countdown-calendar (0:00-0:25) - emotion: INTRO

| # | Time | Line |
|---|---|---|
| I1 | 0:02 | [breath] Maya Torres did everything right. |
| I2 | 0:06 | Two years at De Anza College. Straight A's. Sixty-one units, aimed at UC San Diego. |
| I3 | 0:13 | Then the letter came. [pause] Eighteen units of A-grade work - denied. |
| I4 | 0:18 | Sixteen thousand dollars on the line, and days left to appeal. |
| I5 | 0:22 | [breath] The countdown stopped at one day. [pause] Here's why. |

### DEMO - over the screen recording (0:25-1:30)

Emotion DEMO A:

| # | Time | Line |
|---|---|---|
| D1 | 0:26 | One day left, Maya opens Foothold. Her college. Her university. Her major. |
| D2 | 0:32 | Then she pastes her transcript - the whole thing. Every course snaps into a chip. |
| D3 | 0:39 | And the wall fills in. Green transfers cleanly - her calculus, her physics, her data structures. Amber is at risk. Red doesn't articulate at all. |

Emotion DEMO B:

| # | Time | Line |
|---|---|---|
| D4 | 0:48 | Trap one: her C plus plus courses. Nine units of straight A's - worth nothing for this major. The agreement wants the Java path. |
| D5 | 0:57 | Trap two: she finished two courses of a three-course bundle. [pause] Partial series grant nothing. |
| D6 | 1:04 | And none of this is AI guessing. The verdict comes straight from the official articulation agreement - evaluated line by line, every finding cited. |
| D7 | 1:13 | Caught today, the fix costs about three hundred forty dollars at De Anza. |
| D8 | 1:18 | But nine of those units? [pause] She can still fight for them. |

Emotion CLIMAX (music peaks and cuts at the Draft Petition click ~1:22; beat of silence; soft ding; letter zooms):

| # | Time | Line |
|---|---|---|
| D9 | 1:26 | [breath] She's not asking for a favor. [pause] She's showing them their own agreement. |

### OUTRO - over countdown-resolution (1:30-1:55) - emotion: OUTRO

| # | Time | Line |
|---|---|---|
| O1 | 1:31 | Submitted, one day early. [pause] Nine units - approved on appeal. |
| O2 | 1:36 | The rest was a three hundred forty-two dollar fix at De Anza - not a fifteen thousand, six hundred eighty-six dollar quarter at UCSD. |
| O3 | 1:43 | One hundred sixteen community colleges. Eighty thousand transfer students a year. [pause] Same agreements. Same traps. |
| O4 | 1:50 | [breath] Foothold. [pause] Don't lose the credits you already earned. |

## TTS Input Normalization Rules

- All numbers are already written out as words in the lines above; keep them as words in the TTS input.
- "C plus plus" is spelled out on purpose; do not send "C++" to the model.
- "UCSD" should be sent as "U C S D" if the model reads it as a word.
- "A's" (the grade) should be sent as "A's"; if the model mangles it, use "straight A grades".
- If a cue tag ([breath], [pause]) is not in the model's supported token set, DELETE it; never let an unsupported tag be spoken literally.

## Output Spec

- One WAV per line, 48 kHz, mono, named `vo_<segment>_<line>.wav` (e.g. `vo_intro_I1.wav`, `vo_demo_D4.wav`, `vo_outro_O2.wav`).
- Three takes for the emotional load-bearing lines (I5, D9, O4); one take is fine elsewhere.
- Leave ~0.3s of silence at head and tail of each file for editing room in Resolve.

## Mix Reminders (from AUDIO_TOOLCHAIN.md)

- Music ~-25 dB under the voice, ducked further during narration.
- UI click SFX ~-20 dB relative to voice.
- Music climbs through the demo, peaks and CUTS at the Draft Petition click, silence, soft ding, then D9 lands in the quiet.
- Captions are mandatory; judges watch muted.
