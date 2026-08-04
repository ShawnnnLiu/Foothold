import { useEffect, useRef } from "react";

import "./FoilButton.css";

// The ASCENT.md foil-CTA exception (amendment 2026-08-03): Gold finish, Prism
// lines texture, no runtime finish switching. The sheen is a pure function of
// cursor position (support.js `_onFoilMove` translated); the prototype's PRNG
// idle-flash loop is dropped entirely. Disabled renders the flat treatment.
// Second amendment (2026-08-03): the landing demo button renders the Rainbow
// finish; `finish` is fixed per call site, still never switched at runtime.
// Landing amendment (2026-08-04): the marketing landing renders the landing
// CTA as the export's pill shape (borderless, 999px radius, soft shadow),
// still Gold with the pointer-driven sheen; app screens keep the tile shape.
export default function FoilButton({
  children,
  onClick,
  disabled = false,
  frame = "slate",
  size = "md",
  finish = "gold",
  shape = "tile",
  title,
}: {
  children: string;
  onClick?: () => void;
  disabled?: boolean;
  frame?: "slate" | "chalk";
  size?: "lg" | "md" | "sm";
  finish?: "gold" | "rainbow";
  shape?: "tile" | "pill";
  title?: string;
}) {
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (disabled) {
      return;
    }
    const el = ref.current;
    if (!el) {
      return;
    }
    let raf = 0;
    const onMove = (event: MouseEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        if (!r.width) {
          return;
        }
        const nx = (event.clientX - r.left) / r.width;
        const ny = (event.clientY - r.top) / r.height;
        const dx = Math.max(r.left - event.clientX, 0, event.clientX - r.right);
        const dy = Math.max(r.top - event.clientY, 0, event.clientY - r.bottom);
        const influence = Math.max(0, 1 - Math.hypot(dx, dy) / 180);
        el.style.setProperty("--ft", ".12s");
        el.style.setProperty("--rx", `${((0.5 - ny) * 5 * influence).toFixed(2)}deg`);
        el.style.setProperty("--ry", `${((nx - 0.5) * 7 * influence).toFixed(2)}deg`);
        el.style.setProperty("--mx", `${(50 + (nx * 100 - 50) * influence).toFixed(1)}%`);
        el.style.setProperty("--my", `${(50 + (ny * 100 - 50) * influence).toFixed(1)}%`);
        el.style.setProperty("--ga", `${(100 + (nx - 0.5) * 40 * influence).toFixed(1)}deg`);
      });
    };
    document.addEventListener("mousemove", onMove);
    return () => {
      document.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [disabled]);

  return (
    <button
      ref={ref}
      className={`foil foil--${size} foil--${frame} foil--${finish} foil--${shape}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {!disabled && (
        <>
          <span className="foil__sheen" />
          <span className="foil__glare" />
          <span className="foil__tex" />
        </>
      )}
      <span className="foil__label">{children}</span>
    </button>
  );
}
