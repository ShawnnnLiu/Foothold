import type { Citation, TriageBucket } from "../lib/api";
import { citationLabel } from "../lib/format";

import "./CitationTag.css";

// Every finding's citation is always rendered (citation axiom): uppercase
// with a highlighter underline in the verdict's hold color.
export default function CitationTag({
  citation,
  majorKey,
  bucket,
  small = false,
}: {
  citation: Citation;
  majorKey: string;
  bucket: TriageBucket;
  small?: boolean;
}) {
  return (
    <span className={`citation citation--${bucket} ${small ? "citation--small" : ""}`}>
      {citationLabel(citation, majorKey)}
    </span>
  );
}
