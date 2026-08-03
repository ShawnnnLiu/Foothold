import type { WallStep } from "../lib/evaluation";

import "./WallChart.css";

// The elevation chart: teal filled secure steps, amber OUTLINED reach steps
// (doc-00 rule 3: chalk fill, 2px amber border, replacing the prototype's
// chrome gradient), dashed final steps. Two geometries: the sidebar's
// staggered ascent and the theater's rising blocks. Every animation delay is
// a pure function of the step index; reduced motion zeroes it via tokens.css.

// Theater geometry, copied from the prototype's seven blocks.
const THEATER_WIDTHS = [58, 54, 54, 50, 54, 54, 46];
const THEATER_HEIGHTS = [52, 74, 96, 118, 140, 162, 188];
const THEATER_DELAYS = [0.1, 0.55, 1.0, 1.45, 1.9, 2.35, 2.8];

export default function WallChart({
  steps,
  variant,
}: {
  steps: WallStep[];
  variant: "sidebar" | "theater";
}) {
  if (steps.length === 0) {
    return null;
  }
  return (
    <div className={`wall wall--${variant}`}>
      {steps.map((step, i) => (
        <div
          key={i}
          className={`wall__step wall__step--${step.kind}`}
          style={
            variant === "sidebar"
              ? {
                  marginLeft: 18 * i,
                  animationDelay: `${(0.1 + 0.2 * i).toFixed(1)}s, ${(0.6 + 1.7 * i).toFixed(1)}s`,
                }
              : {
                  width: THEATER_WIDTHS[i % THEATER_WIDTHS.length],
                  height: THEATER_HEIGHTS[i % THEATER_HEIGHTS.length],
                  animationDelay: `${THEATER_DELAYS[i % THEATER_DELAYS.length]}s, ${((THEATER_DELAYS[i % THEATER_DELAYS.length] ?? 0) + 0.1).toFixed(2)}s`,
                }
          }
        />
      ))}
    </div>
  );
}
