import type { Finding } from "../lib/api";
import { formatUnits } from "../lib/format";
import CitationTag from "./CitationTag";
import ReasonTag from "./ReasonTag";

import "./CourseCard.css";

// One finding as a board card. `variant` picks the row's treatment: full-width
// (clean / no-articulation), the at-risk grid cell, or the dashed still-owed
// row. Layout and copy from the prototype's triage section.
export default function CourseCard({
  finding,
  titles,
  majorKey,
  variant,
  onFixChip,
}: {
  finding: Finding;
  titles: Record<string, string | null>;
  majorKey: string;
  variant: "clean" | "at_risk" | "no_articulation" | "still_owed";
  onFixChip?: () => void;
}) {
  const unresolved = finding.code === "unresolved";
  const note =
    finding.advisements.length > 0 ? `"${finding.advisements.join("; ")}"` : finding.detail;

  if (variant === "at_risk") {
    return (
      <div className="cell">
        <div className="cell__line">
          {finding.student_course_codes.map((code) => (
            <span key={code}>
              <b>{code}</b> {titles[code]}{" "}
            </span>
          ))}
          {unresolved && <span className="cell__muted">(unresolved)</span>}
          {finding.receiving_course_code && <b>→ {finding.receiving_course_code}</b>}
        </div>
        <div className="cell__tags">
          <ReasonTag code={finding.code} />
          {note && <span className="cell__note">{note}</span>}
          {unresolved && onFixChip && (
            <span className="cell__note">
              Not in the course list -{" "}
              <span className="cell__fix" onClick={onFixChip}>
                fix the chip
              </span>
            </span>
          )}
        </div>
        <div className="cell__foot">
          {finding.citation ? (
            <CitationTag
              citation={finding.citation}
              majorKey={majorKey}
              bucket={finding.bucket}
              small
            />
          ) : (
            <span className="cell__muted">No citation</span>
          )}
          <span className={`cell__units ${finding.citation ? "" : "cell__muted"}`}>
            {finding.citation ? `${formatUnits(finding.units)} U` : "-"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={`card card--${variant}`}>
      <div className="card__body">
        <div className="card__line">
          {variant === "still_owed" ? (
            <b>{finding.detail}</b>
          ) : (
            <>
              {finding.student_course_codes.map((code) => (
                <span key={code}>
                  <b>{code}</b> {titles[code]}{" "}
                </span>
              ))}
              {finding.receiving_course_code && (
                <>
                  <b>→</b> <b>{finding.receiving_course_code}</b> {finding.receiving_course_title}
                </>
              )}
            </>
          )}
        </div>
        <div className="card__cite">
          {finding.citation ? (
            <CitationTag citation={finding.citation} majorKey={majorKey} bucket={finding.bucket} />
          ) : (
            <span className={`citation citation--${finding.bucket}`}>
              {finding.detail ?? "No published articulation applies this course to this major"}
            </span>
          )}
        </div>
      </div>
      <div className="card__units">{formatUnits(finding.units)} UNITS</div>
    </div>
  );
}
