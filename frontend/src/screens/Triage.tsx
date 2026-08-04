import { useCallback, useState } from "react";

import ArbitragePanel from "../components/ArbitragePanel";
import CourseCard from "../components/CourseCard";
import ErrorBanner from "../components/ErrorBanner";
import FoilButton from "../components/FoilButton";
import HoldTile from "../components/HoldTile";
import { useCountUp, roundTenth } from "../components/useCountUp";
import WallChart from "../components/WallChart";
import Wordmark from "../components/Wordmark";
import type { ArbitrageResponse, Evaluation } from "../lib/api";
import { errorText, fetchArbitrage } from "../lib/client";
import { buildTriageBoard, studentTitleMap, wallSteps } from "../lib/evaluation";
import { countLine, formatDollars, formatUnits, wallCaption } from "../lib/format";
import type { RouteContext } from "../lib/route";

import "./Triage.css";

// Terrace indents: fixed per-row steps from the row's position in the locked
// bucket order (doc 03), never free-form.
const TERRACE_INDENTS = [0, 34, 68, 102];

// Row entrance stagger, bottom-up like the prototype: delay is a pure
// function of the row's stable position.
function rowDelay(position: number): string {
  return `${(0.05 + 0.15 * (3 - position)).toFixed(2)}s`;
}

export default function Triage({
  route,
  evaluation,
  onEditCourses,
  onChangeRoute,
}: {
  route: RouteContext;
  evaluation: Evaluation;
  onEditCourses: () => void;
  onChangeRoute: () => void;
}) {
  const board = buildTriageBoard(evaluation);
  const titles = studentTitleMap(evaluation);
  const steps = wallSteps(board.header);
  const [captionTop, captionBottom] = wallCaption(board.header);
  const majorKey = evaluation.major_key;

  // The arbitrage tab fetches on first activation and caches in component
  // state for the session (doc 04); the server ranking is rendered as-is.
  const [tab, setTab] = useState<"board" | "arbitrage">("board");
  const [arbitrage, setArbitrage] = useState<ArbitrageResponse | null>(null);
  const [arbitrageError, setArbitrageError] = useState<string | null>(null);

  const loadArbitrage = useCallback(() => {
    setArbitrageError(null);
    fetchArbitrage(evaluation.evaluation_id)
      .then(setArbitrage)
      .catch((e: unknown) => setArbitrageError(errorText(e)));
  }, [evaluation.evaluation_id]);

  const openArbitrage = () => {
    setTab("arbitrage");
    if (arbitrage === null && arbitrageError === null) {
      loadArbitrage();
    }
  };

  const clean = useCountUp(board.header.clean_units);
  const risk = useCountUp(board.header.at_risk_units);
  const lost = useCountUp(board.header.no_articulation_units);
  const owed = useCountUp(board.header.still_owed_units);
  const riskDollars = useCountUp(board.header.at_risk_dollars ?? 0);
  const lostDollars = useCountUp(board.header.no_articulation_dollars ?? 0);

  return (
    <div className="triage">
      <div className="triage__sidebar">
        <Wordmark size="sm" frame="chalk" onClick={onChangeRoute} />
        <div>
          <div className="triage__route">
            {route.sending.name} → {route.receiving.name}
          </div>
          <div className="triage__routesub">
            {route.major.label}
            <br />
            Agreement year {evaluation.year_label}
          </div>
        </div>
        <div>
          <div className="triage__walltitle">THE WALL</div>
          <WallChart steps={steps} variant="sidebar" />
          <div className="triage__wallcaption">
            {captionTop}
            <br />
            {captionBottom}
          </div>
        </div>
        <div className="triage__totals">
          <div className="triage__total">
            <HoldTile bucket="transfers_clean" size={20} frame="chalk" />
            <div className="triage__totalbody">
              <div className="triage__totalunits">
                {formatUnits(roundTenth(clean))} <span>UNITS</span>
              </div>
              <div className="triage__totallabel">TRANSFERS CLEAN</div>
            </div>
          </div>
          <div className="triage__total">
            <HoldTile bucket="at_risk" size={20} frame="chalk" />
            <div className="triage__totalbody">
              <div className="triage__totalunits">
                {formatUnits(roundTenth(risk))} <span>UNITS</span>
              </div>
              <div className="triage__totallabel">
                AT RISK
                {board.header.at_risk_dollars !== null && ` · ${formatDollars(riskDollars)}`}
              </div>
            </div>
          </div>
          <div className="triage__total">
            <HoldTile bucket="no_articulation" size={20} frame="chalk" />
            <div className="triage__totalbody">
              <div className="triage__totalunits">
                {formatUnits(roundTenth(lost))} <span>UNITS</span>
              </div>
              <div className="triage__totallabel">
                WON'T TRANSFER
                {board.header.no_articulation_dollars !== null &&
                  ` · ${formatDollars(lostDollars)}`}
              </div>
            </div>
          </div>
          <div className="triage__total">
            <HoldTile bucket="still_owed" size={20} frame="chalk" />
            <div className="triage__totalbody">
              <div className="triage__totalunits">
                {formatUnits(roundTenth(owed))} <span>UNITS</span>
              </div>
              <div className="triage__totallabel">STILL NEEDED</div>
            </div>
          </div>
        </div>
        <div className="triage__foot">
          <FoilButton
            size="sm"
            frame="chalk"
            disabled
            title="Petition drafting arrives with the letter writer"
          >
            Draft petition letter
          </FoilButton>
          <div className="triage__footnote">
            Every result comes straight from ASSIST.org, the official California transfer
            database - each card cites its exact line.
          </div>
        </div>
      </div>

      <div className="triage__board">
        <div className="triage__tabs">
          <div
            className={`triage__tab ${tab === "board" ? "triage__tab--active" : ""}`}
            onClick={() => setTab("board")}
          >
            YOUR CREDITS
          </div>
          <div
            className={`triage__tab ${tab === "arbitrage" ? "triage__tab--active" : ""}`}
            onClick={openArbitrage}
          >
            SAVE MONEY
          </div>
          <div className="triage__edit" onClick={onEditCourses}>
            ← EDIT COURSES
          </div>
        </div>
        {tab === "arbitrage" ? (
          arbitrageError !== null ? (
            <div className="triage__arbstatus">
              <ErrorBanner message={arbitrageError} onRetry={loadArbitrage} />
            </div>
          ) : arbitrage === null ? (
            <div className="triage__arbstatus triage__arbstatus--loading">
              Ranking open courses…
            </div>
          ) : (
            <ArbitragePanel
              sendingName={route.sending.name}
              majorKey={majorKey}
              data={arbitrage}
            />
          )
        ) : (
        <div className="triage__rows">
          <div
            className="triage__row"
            style={{ marginLeft: TERRACE_INDENTS[0], animationDelay: rowDelay(0) }}
          >
            <div className="triage__rowhead">
              <HoldTile bucket="transfers_clean" size={30} frame="slate" shadow />
              <span className="triage__rowtitle">TRANSFERS CLEAN</span>
              <span className="triage__rowcount">
                {countLine(board.columns.transfers_clean.length, board.header.clean_units)}
              </span>
            </div>
            <div className="triage__stack">
              {board.columns.transfers_clean.map((finding, i) => (
                <CourseCard
                  key={i}
                  finding={finding}
                  titles={titles}
                  majorKey={majorKey}
                  variant="clean"
                />
              ))}
            </div>
          </div>

          <div
            className="triage__row triage__row--jut"
            style={{ marginLeft: TERRACE_INDENTS[1], animationDelay: rowDelay(1) }}
          >
            <div className="triage__rowhead">
              <HoldTile bucket="at_risk" size={30} frame="slate" shadow />
              <span className="triage__rowtitle">AT RISK</span>
              <span className="triage__rowcount">
                {countLine(board.columns.at_risk.length, board.header.at_risk_units)}
                {board.header.at_risk_dollars !== null &&
                  ` · ${formatDollars(board.header.at_risk_dollars)} AT STAKE`}
              </span>
            </div>
            <div className="triage__grid">
              {board.columns.at_risk.map((finding, i) => (
                <CourseCard
                  key={i}
                  finding={finding}
                  titles={titles}
                  majorKey={majorKey}
                  variant="at_risk"
                  onFixChip={onEditCourses}
                />
              ))}
            </div>
          </div>

          <div
            className="triage__row"
            style={{ marginLeft: TERRACE_INDENTS[2], animationDelay: rowDelay(2) }}
          >
            <div className="triage__rowhead">
              <HoldTile bucket="no_articulation" size={30} frame="slate" shadow />
              <span className="triage__rowtitle">WON'T TRANSFER</span>
              <span className="triage__rowcount">
                {countLine(
                  board.columns.no_articulation.length,
                  board.header.no_articulation_units,
                )}
                {board.header.no_articulation_dollars !== null &&
                  ` · ${formatDollars(board.header.no_articulation_dollars)}`}
              </span>
            </div>
            <div className="triage__stack">
              {board.columns.no_articulation.map((finding, i) => (
                <CourseCard
                  key={i}
                  finding={finding}
                  titles={titles}
                  majorKey={majorKey}
                  variant="no_articulation"
                />
              ))}
            </div>
          </div>

          <div
            className="triage__row"
            style={{ marginLeft: TERRACE_INDENTS[3], animationDelay: rowDelay(3) }}
          >
            <div className="triage__rowhead">
              <HoldTile bucket="still_owed" size={30} frame="slate" />
              <span className="triage__rowtitle">STILL NEEDED</span>
              <span className="triage__rowcount">
                LEFT TO TAKE FOR THIS MAJOR · {formatUnits(board.header.still_owed_units)} UNITS
              </span>
            </div>
            <div className="triage__stack">
              {board.still_owed.map((finding, i) => (
                <CourseCard
                  key={i}
                  finding={finding}
                  titles={titles}
                  majorKey={majorKey}
                  variant="still_owed"
                />
              ))}
            </div>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
