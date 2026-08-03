import type { EvaluationFindingCode } from "../lib/api";
import { REASON_TAGS } from "../lib/format";

import "./ReasonTag.css";

// Bordered pill naming the at-risk reason; text from the locked doc-02 map.
export default function ReasonTag({ code }: { code: EvaluationFindingCode }) {
  const label = REASON_TAGS[code];
  return label ? <span className="reasontag">{label}</span> : null;
}
