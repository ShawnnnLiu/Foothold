# Demo Video Audio And Editing Toolchain

Free-tool plan for the 2-minute Pathfinders demo video: recording, editing, music, sound effects, and voice processing.

## Recording And Editing

- **Screen Studio** (already installed) records the screen plus microphone and system audio, with per-clip mute/volume, automatic zooms, and cursor smoothing.
  It is not a mixer: no multi-track audio, no music beds, no sound effect placement.
- **DaVinci Resolve (free)** is the editor of choice for final assembly.
  The Edit page handles the cut (cold open, screen recordings, title cards); ignore Fusion and Color.
  The Fairlight page provides unlimited audio tracks for voiceover, music, and frame-accurate SFX placement.
- Export from Screen Studio at the final resolution and frame rate, and set the Resolve timeline to match before importing, so nothing gets rescaled twice.

## Voiceover Workflow

- Record the final voiceover as a separate audio-only pass against the edited picture, not while driving the demo.
  Narrating and clicking simultaneously produces rushed pacing and breathing artifacts.
- Record in a quiet room, close to the mic.
  Even AirPods beat a laptop mic across the room; a wired/USB mic beats both.

## Free Music And SFX Sources

- **Pixabay** (top pick): large music and SFX library, free for commercial use, no attribution required.
  Good for build-up tracks and UI click sounds.
- **Mixkit**: smaller but well curated, free, no attribution; strong tech/corporate music section.
- **YouTube Audio Library** (via YouTube Studio): filter by "attribution not required"; safe from copyright claims when publishing on YouTube.
- **Freesound.org**: deepest SFX library; licenses vary per file, so filter to CC0.

SFX search terms that work: "ui click", "pop", "soft click", "tap".

Since the demo is a public contest submission, use only no-attribution or properly attributed tracks, and note sources in the video description or write-up.

## Voice Processing

- **Adobe Podcast Enhance** (podcast.adobe.com/enhance): free web tool that removes room echo and noise; the biggest quality jump for zero cost.
  Keep the strength slider around 50-70% to avoid an over-processed sound.
  It is an AI tool: if used, it must go on the contest's mandatory AI tools disclosure list.
- **DaVinci Resolve Fairlight** (non-AI route): noise reduction, EQ (high-pass at ~80 Hz, presence boost around 3-5 kHz), and a compressor.
  That chain alone gets ~80% of podcast sound.
- **Audacity**: fine for manual cleanup, but redundant if already working in Resolve.

## Mix Targets

- UI click SFX around -20 dB relative to voice; keep them subtle.
- Music around -25 dB under the voice, ducked further during narration-heavy moments.

## Suggested Pipeline

1. Record screen takes in Screen Studio (scratch narration optional, for timing only).
2. Export takes at final resolution/frame rate.
3. Assemble the cut in Resolve on a matching timeline.
4. Record the voiceover as a separate pass against the edited picture.
5. Run the voiceover through Adobe Podcast Enhance at moderate strength (and add it to the AI tools list), or use the Fairlight chain instead.
6. Mix voice, music, and SFX to the targets above; export.

## Disclosure Notes

- Screen Studio, Resolve, Pixabay, Mixkit, and Freesound need no AI disclosure by themselves.
- Any AI feature used inside the tools (Adobe Podcast Enhance, CapCut auto-captions, Resolve AI audio cleanup) should be added to the contest tools list.

Final production actuals (2026-08-20):

- ElevenLabs generated the voiceover (TTS; replaced the K2-FSA Omnivoice plan) - disclosed.
- CapCut auto-captions generated the captions - disclosed.
- Adobe Podcast Enhance was NOT used - no disclosure needed.
- DaVinci Resolve AI audio cleanup was NOT used - no disclosure needed.
- The Claude in Chrome extension drove browser verification of the video assets and app - disclosed.
