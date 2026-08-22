# Foothold demo video - context handoff (2026-08-06)

Carry-over context for the next working session (resolution animation and remaining video work).

## Where this fits

Stellic Pathfinders judging is five equal criteria with non-technical judges valuing helpfulness over technical complexity.
Strategy settled on: the product is already past the "how well it's built" bar; remaining effort goes to the 2-min video, the 500-word write-up, and demo-path polish.
The write-up must explicitly name Transferology (lookup table vs transcript-in/verdict-out differentiation) and frame Foothold as upstream/student-side of Stellic's institutional world.

## Video narrative (locked)

1. Cold open (~0:00-0:22): calendar counting down to a transfer-credit appeal deadline.
   No student biography (rejected as sob-story risk) - stakes carried by the numbers and by "Grade: A" next to red denials.
   The clock stops at 1 day left, never zero: Foothold is why.
2. Demo (~0:22-1:15): played as "her last day" - transcript paste, chips resolve, triage wall fills.
   Music climbing throughout.
3. Climax (~1:15-1:35): she clicks Draft Petition, music peaks and cuts, beat of silence, soft ding, the letter appears zoomed on the line citing the agreement.
   Line: "She's not asking for a favor. She's showing them their own agreement."
4. Close (~1:35-2:00): quiet VO, scale claim (116 CCs, ~80,000 corridor transfers/yr), link card.

## Production stack (solo)

Script written first (~280-300 words for 2 min).
Screen Studio (~$89) for capture with auto-zoom and cursor smoothing; separate scene clips, 2-3 takes each.
VO generated line-by-line with ElevenLabs TTS (switched from K2-FSA Omnivoice 2026-08-20); no AI voice cleanup applied.
Assembled in CapCut with its auto-captions; music from the CapCut library or uppbeat.io.
AI disclosure from this stack: ElevenLabs and CapCut auto-captions; Adobe Podcast Enhance and Resolve AI audio cleanup were not used.
Upload to Loom or YouTube unlisted.
Captions are mandatory (judges watch muted).

## Demo student (verified live vs assist.org 2026-08-06)

Maya Torres (fictional name, real data), De Anza -> UCSD CSE B.S.
Agreement key `76/113/to/7/Major/76ab1c59-2dcf-4c6f-f364-08ddd3b241a4`, 2025-26 year, matches local articulation.db.
Traps:

- CIS 22A/22B (9u, all A's) articulate to nothing for this major (CSE 11 needs the Java path or CIS 36B).
- CIS 21JA + 21JB done but CIS 26B missing, so the CSE 30 three-course AND-bundle grants nothing (9u at risk).
- CSE 21/29 have no De Anza articulation at all - impossible to complete before transfer.

Money (2026-27): extra UCSD quarter $15,686; total exposure $16,244; pre-transfer fix ~$342 - the ~46x punchline for the VO close.
Caveat to keep honest: 22A/22B are worthless for this major's articulation, not in general - the at-risk / no-articulation triage distinction.

## Built and verified this session

`docs/video/countdown-calendar.html` - the cold-open asset, video-only (not product code).
Slate background, exact Ascent tokens (chalk/slate/hold-red, Archivo, hard offset shadows).
Left: evaluation card listing all four denied courses with grades and red x marks, pill "NOT ACCEPTED · 18 UNITS", appeal fine print.
Right: real-weekday September calendar, Friday the 25th hand-ringed with an "APPEAL DUE" tag.
Days cross off with accelerating hand-drawn X's (~15s); the counter shifts slate -> amber -> red; ends with screen dim, "1 DAY LEFT" stamp slam + shake, "$15,686 ON THE LINE" subline.
Controls: SPACE play, R reset, `?speed=` multiplier; hidden cursor; all timings deterministic so takes are frame-identical.
Bugs found and fixed via live browser verification: overlay z-index (day numbers have `z-index: 1`, overlays needed explicit 10/20/30), "1 DAYS" grammar, ring centered on the deadline day.
Screen-record it fullscreen in Chrome; hold the final stamped frame under the remaining VO.

Polish pass 2026-08-06 (second session), aimed at the five equal judging criteria on stellic.com/pathfinders:

- The "Grade: A" irony is now sold: grades are bold, full-opacity, ringed with hand-drawn teal ellipses (a teacher's mark) so the eye ping-pongs A vs red ✗ even muted on a laptop.
- Fonts are self-contained: `docs/video/fonts.css` inlines the Archivo variable woff2 as a data URI; no Google Fonts CDN, so capture works fully offline (flight-safe) with zero font flash.
- Amber counter window widened to <=10 days and red to <=5 so the color escalation reads as phases despite the accelerating crossing pace.
- Deadline moved from Saturday the 26th to Friday the 25th (real appeal deadlines fall on business days; the calendar shows true weekdays, so this was checkable).
- Operator hint auto-fades after 5s idle, so head frames are clean before SPACE.
- `.left` is a fixed 460px in BOTH assets; this is a frame-match contract with the resolution file (below). Do not turn it back into max-width.

`docs/video/countdown-resolution.html` - the resolution bookend, built this session.
It opens frame-matched to the cold open's final frame (dim, red stamp, "$15,686 ON THE LINE", counter at 1 DAY, calendar crossed through the 24th), then reverses it; where the cold open accelerates into panic, the resolution decelerates into calm.
Beat timeline (1x, from SPACE): 0.9s red stamp falls off screen, dim lifts, calendar fades to ghost; 1.3s teal postmark "SUBMITTED SEP 24 · 1 DAY EARLY" slams onto the card corner; 2.7s/3.8s the CIS 21JA and 21JB red x's flip to hand-drawn teal checks; 5.2-5.5s pill re-stamps "APPROVED ON APPEAL · 9 UNITS"; 6.9s the 22A/22B rows fade and the fine print becomes "The other 9 units? A $342 fix, if caught before transfer."; 8.5s "$15,686 SAVED" rises where the day counter was; 12.8s crossfade to the scale screen ("116 COMMUNITY COLLEGES." / "~80,000 TRANSFER STUDENTS A YEAR.") and at 16s the FOOTHOLD link card (headline "Don't lose the credits you already earned.") rises and holds for the VO.
Deliberately honest: only the 9 at-risk units flip to approved; 22A/22B stay denied and become the $342 counterfactual caption, which is the at-risk vs no-articulation triage distinction on camera and the springboard into the scale claim.
Same controls and determinism as the cold open.
The link card reads `foothold-transfer.com` (domain purchased 2026-08-07, to be pointed at the Fly app `foothold`).

Verification note: both assets were verified in live Chrome; end-state DOM class snapshots confirmed every beat fires in order with a clean console.
The Chrome extension's screenshots of mid-animation states sometimes produce stale-tile composites (impossible mixed states); trust DOM snapshots or real playback, not extension screenshots.

## Next up

The full VO script beat sheet (~280-300 words) against the locked narrative, now including the resolution beats above.
The 500-word write-up (structure agreed: hook -> mechanism in plain language -> Transferology differentiation -> scale arithmetic -> upstream-of-Stellic close).
Recording: the two HTML assets and rough-cutting work offline; the demo segment needs internet because both LLM nodes (transcript parse, petition draft) are live request-time calls.
