import { useEffect, useState } from "react";

import { prefersReducedMotion } from "./motion";

// Sidebar count-up (ASCENT.md motion): eases 0 -> target over a fixed
// duration with cubic ease-out; the target is the deterministic total and the
// final frame is exactly it. Under reduced motion the target renders
// immediately, no animation.
const DURATION_MS = 1200;

export function useCountUp(target: number): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0));

  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / DURATION_MS);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);
      if (progress < 1) {
        raf = requestAnimationFrame(step);
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  return value;
}

// Display rounding for mid-animation frames; the final frame is the exact
// deterministic total, untouched.
export function roundTenth(value: number): number {
  return Math.round(value * 10) / 10;
}
