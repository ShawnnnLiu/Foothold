import { useEffect, useRef } from "react";

import type { WallStep } from "../lib/evaluation";

import "./WallChart.css";

// The elevation chart: teal filled secure steps, amber OUTLINED reach steps
// (doc-00 rule 3: chalk fill, 2px amber border, replacing the prototype's
// chrome gradient), dashed final steps. Two geometries: the sidebar's
// staggered ascent and the theater's rising blocks. Entrance and sheen
// timings are per-step prototype constants indexed by stable position;
// reduced motion zeroes them via tokens.css.
//
// The sidebar wall additionally runs the prototype's ambient "chance events"
// (`_nextEvent` translated): PRNG-timed holoflash/cascade/brightness-pop
// effects on the sheen-bearing steps. This is the bounded PRNG exception in
// the CLAUDE.md determinism axiom (third ASCENT.md amendment, 2026-08-03):
// presentation-only ambience that never touches layout, data, or workflow
// state, and is skipped under prefers-reduced-motion.

// Theater geometry, copied from the prototype's seven blocks.
const THEATER_WIDTHS = [58, 54, 54, 50, 54, 54, 46];
const THEATER_HEIGHTS = [52, 74, 96, 118, 140, 162, 188];
const THEATER_DELAYS = [0.1, 0.55, 1.0, 1.45, 1.9, 2.35, 2.8];

// Sheen timings, copied from the prototype's six filled steps: the sidebar
// wall loops fh-wallsheen forever on these durations/delays; the theater
// blocks fire fh-sweep once.
const SIDEBAR_SHEEN_DURATIONS = [6.2, 7.1, 5.8, 7.6, 6.6, 7.9];
const SIDEBAR_SHEEN_DELAYS = [0.6, 2.3, 1.1, 3.4, 1.9, 4.1];
const THEATER_SWEEP_DURATIONS = [1.2, 1.15, 1.45, 1.25, 1.5, 1.3];
const THEATER_SWEEP_DELAYS = [0.25, 0.62, 1.08, 1.55, 1.98, 2.45];

export default function WallChart({
  steps,
  variant,
}: {
  steps: WallStep[];
  variant: "sidebar" | "theater";
}) {
  const wallRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (variant !== "sidebar") {
      return;
    }
    const wall = wallRef.current;
    if (!wall) {
      return;
    }
    const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timers: number[] = [];
    let evT = 0;
    const nextEvent = () => {
      evT = window.setTimeout(
        () => {
          if (!reduced()) {
            const sheenSteps = [...wall.children].filter(
              (c): c is HTMLElement =>
                c instanceof HTMLElement &&
                (c.classList.contains("wall__step--secure") ||
                  c.classList.contains("wall__step--reach")),
            );
            const flash = (el: HTMLElement, d = 0) => {
              const orig = el.style.cssText;
              el.style.animation = `fh-stepin 0s both, fh-holoflash ${(0.9 + Math.random() * 0.6).toFixed(2)}s ease-in-out ${d}ms both`;
              timers.push(
                window.setTimeout(() => {
                  el.style.cssText = orig;
                }, d + 1800),
              );
            };
            const roll = Math.random();
            if (sheenSteps.length) {
              if (roll < 0.45) {
                const el = sheenSteps[Math.floor(Math.random() * sheenSteps.length)];
                if (el) {
                  flash(el);
                }
              } else if (roll < 0.75) {
                sheenSteps.forEach((el, i) => flash(el, i * 140));
              } else {
                const el = sheenSteps[Math.floor(Math.random() * sheenSteps.length)];
                if (el) {
                  el.style.transition = "filter .25s ease, box-shadow .25s ease";
                  el.style.filter = "brightness(1.7) saturate(1.6)";
                  el.style.boxShadow = "0 0 14px rgba(255,255,255,.75)";
                  timers.push(
                    window.setTimeout(() => {
                      el.style.filter = "";
                      el.style.boxShadow = "";
                    }, 340),
                  );
                }
              }
            }
          }
          nextEvent();
        },
        3500 + Math.random() * 5500,
      );
    };
    nextEvent();
    return () => {
      clearTimeout(evT);
      timers.forEach(clearTimeout);
    };
  }, [variant]);

  if (steps.length === 0) {
    return null;
  }
  return (
    <div ref={wallRef} className={`wall wall--${variant}`}>
      {steps.map((step, i) => (
        <div
          key={i}
          className={`wall__step wall__step--${step.kind}`}
          style={
            variant === "sidebar"
              ? {
                  marginLeft: 18 * i,
                  animationDuration: `0.35s, ${SIDEBAR_SHEEN_DURATIONS[i % SIDEBAR_SHEEN_DURATIONS.length]}s`,
                  animationDelay: `${(0.1 + 0.2 * i).toFixed(1)}s, ${SIDEBAR_SHEEN_DELAYS[i % SIDEBAR_SHEEN_DELAYS.length]}s`,
                }
              : {
                  width: THEATER_WIDTHS[i % THEATER_WIDTHS.length],
                  height: THEATER_HEIGHTS[i % THEATER_HEIGHTS.length],
                  animationDuration: `0.45s, ${THEATER_SWEEP_DURATIONS[i % THEATER_SWEEP_DURATIONS.length]}s`,
                  animationDelay: `${THEATER_DELAYS[i % THEATER_DELAYS.length]}s, ${THEATER_SWEEP_DELAYS[i % THEATER_SWEEP_DELAYS.length]}s`,
                }
          }
        />
      ))}
    </div>
  );
}
