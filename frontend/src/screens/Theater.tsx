import { useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "../components/motion";
import WallChart from "../components/WallChart";
import type { Evaluation } from "../lib/api";
import { theaterLines, type WallStep } from "../lib/evaluation";

import "./Theater.css";

// The theater's fixed decorative climb (the prototype's seven blocks); the
// honest numbers live in the check lines, which fill ONLY from the response.
const THEATER_STEPS: WallStep[] = [
  { kind: "secure" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "owed" },
];

// Every timing constant is a literal (doc 03); no randomness.
const LINE_INTERVAL_MS = 700;
const EXIT_HOLD_MS = 1100;
const MIN_DISPLAY_MS = 2400;

export default function Theater({
  evaluation,
  onDone,
}: {
  evaluation: Evaluation | null;
  onDone: () => void;
}) {
  const [step, setStep] = useState(-1);
  const mountedAt = useRef(performance.now());

  useEffect(() => {
    if (!evaluation) {
      return;
    }
    if (prefersReducedMotion()) {
      onDone();
      return;
    }
    const timers: number[] = [];
    for (const i of [0, 1, 2, 3]) {
      timers.push(window.setTimeout(() => setStep(i), LINE_INTERVAL_MS * (i + 1)));
    }
    const linesDoneMs = LINE_INTERVAL_MS * 4 + EXIT_HOLD_MS;
    const elapsed = performance.now() - mountedAt.current;
    timers.push(window.setTimeout(onDone, Math.max(linesDoneMs, MIN_DISPLAY_MS - elapsed)));
    return () => timers.forEach((t) => clearTimeout(t));
  }, [evaluation, onDone]);

  const lines = evaluation ? theaterLines(evaluation) : null;

  return (
    <div className="theater">
      <WallChart steps={THEATER_STEPS} variant="theater" />
      <div className="theater__lines">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`theater__row ${step >= i ? "theater__row--done" : ""}`}>
            <span className="theater__box">
              <svg width="13" height="13" viewBox="0 0 20 20" className="theater__mark">
                <path d="M4 10.5l4 4 8-9" stroke="#F3F1EC" strokeWidth="3.5" fill="none" />
              </svg>
            </span>
            <span className="theater__text">{lines ? lines[i] : ""}</span>
          </div>
        ))}
      </div>
      <div className="theater__closing">The agreement decides - not the AI</div>
    </div>
  );
}
