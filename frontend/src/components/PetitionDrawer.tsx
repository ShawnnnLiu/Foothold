import { useEffect, useRef, useState } from "react";

import type { Evaluation, PetitionPollResponse } from "../lib/api";
import { createPetition, errorText, fetchPetition } from "../lib/client";
import { studentTitleMap } from "../lib/evaluation";
import { REASON_TAGS } from "../lib/format";
import {
  POLL_INTERVAL_MS,
  POLL_MAX_ATTEMPTS,
  POST_DEBOUNCE_MS,
  citedHolds,
  defaultSelection,
  letterParagraphs,
  paragraphSegments,
  petitionItems,
  selectionLine,
  toggleSelection,
} from "../lib/petition";

import "./PetitionDrawer.css";

// The letter card's mutually exclusive states. `empty` is the zero-selection
// prompt (the POST requires at least one position); `error` covers transport
// failures, 409/422 bodies, and the poll cap; `failed` is the server's typed
// LLM failure (HTTP 200, status "failed").
type LetterState =
  | { kind: "empty" }
  | { kind: "drafting" }
  | { kind: "letter"; result: PetitionPollResponse }
  | { kind: "failed"; reasonCode: string | null }
  | { kind: "error"; message: string };

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// The doc-F5 petition drawer over the prototype's `Petition drawer` screen:
// overlay + right drawer, checkbox list of the petitionable findings, the
// letter card, copy button, counselor disclaimer. All decisions live in
// lib/petition.ts; this component only fires the wire calls and renders.
export default function PetitionDrawer({
  evaluation,
  onClose,
}: {
  evaluation: Evaluation;
  onClose: () => void;
}) {
  const items = petitionItems(evaluation);
  const titles = studentTitleMap(evaluation);

  const [selected, setSelected] = useState<number[]>(() => defaultSelection(items));
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LetterState>({ kind: "empty" });
  const [copied, setCopied] = useState(false);

  // Stale-response guard: every selection change or retry bumps the
  // generation; in-flight loops from older generations drop their results.
  const generation = useRef(0);

  useEffect(() => {
    const gen = ++generation.current;
    if (selected.length === 0) {
      setState({ kind: "empty" });
      return;
    }
    setState({ kind: "drafting" });
    const positions = [...selected];
    const draft = async () => {
      try {
        const { petition_id } = await createPetition(evaluation.evaluation_id, {
          finding_positions: positions,
        });
        for (let polls = 0; polls < POLL_MAX_ATTEMPTS; polls++) {
          await sleep(POLL_INTERVAL_MS);
          if (generation.current !== gen) {
            return;
          }
          const result = await fetchPetition(petition_id);
          if (generation.current !== gen) {
            return;
          }
          if (result.status === "succeeded") {
            setState({ kind: "letter", result });
            return;
          }
          if (result.status === "failed") {
            setState({ kind: "failed", reasonCode: result.reason_code });
            return;
          }
        }
        setState({
          kind: "error",
          message: "Drafting is taking longer than expected. Retry to try again.",
        });
      } catch (error: unknown) {
        if (generation.current === gen) {
          setState({ kind: "error", message: errorText(error) });
        }
      }
    };
    const timer = setTimeout(() => {
      void draft();
    }, POST_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [selected, attempt, evaluation.evaluation_id]);

  // Closing the drawer abandons any in-flight loop.
  useEffect(() => {
    return () => {
      generation.current += 1;
    };
  }, []);

  const letter = state.kind === "letter" ? state.result : null;
  const holds = letter === null ? {} : citedHolds(letter.cited, evaluation);
  const paragraphs = letter === null ? [] : letterParagraphs(letter.letter_text);

  const copyLetter = () => {
    if (letter?.letter_text == null) {
      return;
    }
    void navigator.clipboard.writeText(letter.letter_text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const retry = () => setAttempt((n) => n + 1);

  return (
    <>
      <div className="petition__overlay" onClick={onClose} />
      <aside className="petition" aria-label="Petition letter">
        <div className="petition__head">
          <h2 className="petition__title">Petition letter</h2>
          <button className="petition__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="petition__count">{selectionLine(selected.length, items.length)}</div>
        <div className="petition__items">
          {items.map(({ position, finding }) => {
            const checked = selected.includes(position);
            const code = finding.student_course_codes.join(" + ");
            return (
              <div
                key={position}
                className="petition__item"
                onClick={() => setSelected(toggleSelection(selected, position))}
              >
                <span className={`petition__box ${checked ? "petition__box--on" : ""}`}>
                  {checked ? "✓" : ""}
                </span>
                <span className="petition__code">{code}</span>
                <span className="petition__coursetitle">
                  {titles[finding.student_course_codes[0] ?? ""] ?? ""}
                </span>
                <span
                  className={`petition__tag petition__tag--${
                    finding.bucket === "no_articulation" ? "red" : "amber"
                  }`}
                >
                  {REASON_TAGS[finding.code] ?? "WON'T TRANSFER"}
                </span>
              </div>
            );
          })}
        </div>
        {letter?.fallback === true && (
          <div className="petition__fallback">Drafted from the template letter</div>
        )}
        <div className="petition__card">
          <div className="petition__cardhead">
            DRAFT - GROUNDED IN THE {evaluation.year_label} AGREEMENT
          </div>
          {state.kind === "empty" && (
            <p className="petition__para petition__para--muted">
              Check at least one item above to draft a letter.
            </p>
          )}
          {state.kind === "drafting" && (
            <div className="petition__skeleton" aria-label="Drafting the letter">
              <div className="petition__bone" />
              <div className="petition__bone" />
              <div className="petition__bone petition__bone--short" />
            </div>
          )}
          {state.kind === "failed" && (
            <div className="petition__failed">
              <p className="petition__para">
                Drafting failed ({state.reasonCode ?? "unknown reason"}). No letter was produced;
                your triage results above are unaffected.
              </p>
              <button className="petition__retry" onClick={retry}>
                Retry
              </button>
            </div>
          )}
          {state.kind === "error" && (
            <div className="petition__failed">
              <p className="petition__para">{state.message}</p>
              <button className="petition__retry" onClick={retry}>
                Retry
              </button>
            </div>
          )}
          {state.kind === "letter" &&
            paragraphs.map((paragraph, i) => (
              <p key={i} className="petition__para">
                {paragraphSegments(paragraph, holds).map((segment, j) =>
                  segment.hold === null ? (
                    <span key={j}>{segment.text}</span>
                  ) : (
                    <span key={j} className={`petition__cite petition__cite--${segment.hold}`}>
                      {segment.text}
                    </span>
                  ),
                )}
              </p>
            ))}
        </div>
        <div className="petition__actions">
          <button
            className="petition__copy"
            disabled={letter?.letter_text == null}
            onClick={copyLetter}
          >
            {copied ? "Copied" : "Copy letter"}
          </button>
          <span className="petition__disclaimer">
            This is a draft - verify with your counselor before submitting.
          </span>
        </div>
      </aside>
    </>
  );
}
