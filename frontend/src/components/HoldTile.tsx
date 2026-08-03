import type { TriageBucket } from "../lib/api";

import "./HoldTile.css";

// Verdict hold-tile per the ASCENT.md verdict table: shape + icon + word,
// never color alone (the word is the neighboring label; the shape and icon
// live here). `still_owed` is the dashed "route ahead" outline variant.
export default function HoldTile({
  bucket,
  size,
  frame,
  shadow = false,
}: {
  bucket: TriageBucket;
  size: number;
  frame: "slate" | "chalk";
  shadow?: boolean;
}) {
  const ink = frame === "slate" ? "#272B31" : "#F3F1EC";
  const icon = size >= 26 ? 16 : 12;
  return (
    <span
      className={`holdtile holdtile--${bucket} holdtile--${frame} ${shadow ? "holdtile--shadow" : ""}`}
      style={{ width: size, height: size }}
    >
      {bucket === "transfers_clean" && (
        <svg width={icon} height={icon} viewBox="0 0 20 20">
          <path d="M4 10.5l4 4 8-9" stroke="#F3F1EC" strokeWidth="3.5" fill="none" />
        </svg>
      )}
      {bucket === "at_risk" && <span className="holdtile__bang">!</span>}
      {bucket === "no_articulation" && (
        <svg width={icon - 2} height={icon - 2} viewBox="0 0 20 20">
          <path d="M5 5l10 10M15 5L5 15" stroke="#F3F1EC" strokeWidth="3.5" />
        </svg>
      )}
      {bucket === "still_owed" && (
        <svg width={icon - 1} height={icon - 1} viewBox="0 0 20 20">
          <path d="M10 16V5M5 9.5L10 4.5l5 5" stroke={ink} strokeWidth="2.5" fill="none" />
        </svg>
      )}
    </span>
  );
}
