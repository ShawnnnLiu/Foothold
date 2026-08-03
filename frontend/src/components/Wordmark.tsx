import "./Wordmark.css";

// The three-step ascending mark at logo scale (ASCENT.md wordmark section);
// rect geometry copied from the prototype. `frame` picks the ink for the
// surface it sits on: slate ink on chalk, chalk ink on the slate sidebar.
export default function Wordmark({
  size,
  frame,
  onClick,
}: {
  size: "lg" | "sm";
  frame: "slate" | "chalk";
  onClick?: () => void;
}) {
  const ink = frame === "slate" ? "#272B31" : "#F3F1EC";
  const width = size === "lg" ? 52 : 24;
  const height = size === "lg" ? 44 : 20;
  return (
    <div
      className={`wordmark wordmark--${size} ${onClick ? "wordmark--link" : ""}`}
      onClick={onClick}
    >
      <svg width={width} height={height} viewBox="0 0 26 22">
        <rect x="0" y="14" width="7" height="8" fill={ink} />
        <rect x="9" y="8" width="7" height="14" fill={ink} />
        <rect x="18" y="1" width="7" height="21" fill="#0E8A6D" stroke={ink} strokeWidth="2" />
      </svg>
      <span className="wordmark__text" style={{ color: ink }}>
        FOOTHOLD
      </span>
    </div>
  );
}
