import type { ArbitrageResponse, ArbitrageRow } from "../lib/api";
import { formatDollars, formatUnits } from "../lib/format";
import CitationTag from "./CitationTag";

import "./ArbitragePanel.css";

// The Mode B tab body: server-ranked rows rendered in wire order, never
// re-sorted here. A null `savings_dollars` renders the card without the
// teal tile (absent, never $0), with the muted no-rate line instead.
export default function ArbitragePanel({
  sendingName,
  majorKey,
  data,
}: {
  sendingName: string;
  majorKey: string;
  data: ArbitrageResponse;
}) {
  return (
    <div className="arb">
      <h2 className="arb__headline">Take it at a community college instead</h2>
      <p className="arb__sub">
        Courses still open at {sendingName} that articulate back to this degree - ranked by
        tuition saved. Savings are illustrative sample data.
      </p>
      {data.rows.length === 0 ? (
        <p className="arb__empty">
          Nothing left to take at {sendingName} - your courses already satisfy every
          articulation the major agreement publishes.
        </p>
      ) : (
        <div className="arb__cards">
          {data.rows.map((row, i) => (
            <ArbitrageCard key={i} row={row} rank={i + 1} majorKey={majorKey} />
          ))}
        </div>
      )}
      {data.omitted_no_rate > 0 && (
        <p className="arb__footnote">
          {data.omitted_no_rate} of these {data.omitted_no_rate === 1 ? "row is" : "rows are"}{" "}
          shown without a savings figure because this campus publishes no per-unit rate.
        </p>
      )}
    </div>
  );
}

function ArbitrageCard({
  row,
  rank,
  majorKey,
}: {
  row: ArbitrageRow;
  rank: number;
  majorKey: string;
}) {
  return (
    <div className="arb__card">
      <div className="arb__rank">#{rank}</div>
      <div className="arb__body">
        <div className="arb__mapping">
          {row.missing_course_codes.map((code, i) => (
            <span key={code}>
              {i > 0 && <span className="arb__joiner"> + </span>}
              <span className="arb__code">{code}</span>
            </span>
          ))}
          <span className="arb__code">
            {" → "}
            {row.receiving_course_code ?? row.receiving_series_name}
          </span>
          {row.receiving_course_title !== null && <span> {row.receiving_course_title}</span>}
        </div>
        <div className="arb__meta">
          <span className="arb__units">{formatUnits(row.units)} UNITS</span>
          <CitationTag
            citation={row.citation}
            majorKey={majorKey}
            bucket="transfers_clean"
            small
          />
        </div>
      </div>
      {row.savings_dollars !== null ? (
        <div className="arb__save">
          <div className="arb__saveamount">{formatDollars(row.savings_dollars)}</div>
          <div className="arb__savelabel">YOU SAVE</div>
        </div>
      ) : (
        <div className="arb__norate">No per-unit rate published for this campus</div>
      )}
    </div>
  );
}
