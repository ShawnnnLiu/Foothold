import { useEffect, useState } from "react";

import ErrorBanner from "../components/ErrorBanner";
import FoilButton from "../components/FoilButton";
import Wordmark from "../components/Wordmark";
import type { CourseHit } from "../lib/api";
import { errorText, searchCourses } from "../lib/client";
import {
  addChip,
  type ChipState,
  loadSample,
  popChip,
  removeChip,
  SAMPLE_COURSES,
  setInput,
  suggestions,
  extractCourseCodes,
} from "../lib/courses";
import { parseMessage, resolveCodes } from "../lib/resolve";
import type { RouteContext } from "../lib/route";

import "./Entry.css";

const DEBOUNCE_MS = 150;

export default function Entry({
  route,
  chipState,
  setChipState,
  banner,
  onRetryBanner,
  onBack,
  onEvaluate,
}: {
  route: RouteContext;
  chipState: ChipState;
  setChipState: (update: (state: ChipState) => ChipState) => void;
  banner: string | null;
  onRetryBanner: () => void;
  onBack: () => void;
  onEvaluate: () => void;
}) {
  const [hits, setHits] = useState<CourseHit[]>([]);
  const [paste, setPaste] = useState("");
  const [parseMsg, setParseMsg] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const search = (q: string) =>
    searchCourses(route.sending.assist_id, q).then((body) => body.courses);

  useEffect(() => {
    const q = chipState.input.trim();
    if (q === "") {
      setHits([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      search(q)
        .then((courses) => {
          if (!cancelled) {
            setHits(courses);
            setLocalError(null);
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setLocalError(errorText(e));
          }
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [chipState.input, route.sending.assist_id]);

  const sugs = suggestions(hits, chipState);

  const accept = (hit: CourseHit) => {
    setChipState((state) => addChip(state, hit));
    setHits([]);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && sugs[0]) {
      event.preventDefault();
      accept(sugs[0]);
    } else if (event.key === "Backspace" && chipState.input === "") {
      setChipState(popChip);
    }
  };

  const onSample = () => {
    resolveCodes([...SAMPLE_COURSES], search)
      .then((result) => {
        setChipState(() => loadSample(result.resolved));
        setParseMsg(result.unresolved.length > 0 ? parseMessage(result) : "");
        setLocalError(null);
      })
      .catch((e: unknown) => setLocalError(errorText(e)));
  };

  const onParse = () => {
    resolveCodes(extractCourseCodes(paste), search)
      .then((result) => {
        setChipState((state) => result.resolved.reduce(addChip, state));
        setParseMsg(parseMessage(result));
        setLocalError(null);
      })
      .catch((e: unknown) => setLocalError(errorText(e)));
  };

  return (
    <div className="entry">
      <div className="entry__bar">
        <Wordmark size="sm" frame="slate" onClick={onBack} />
        <div className="entry__context">
          <span className="entry__contextname">{route.sending.name}</span>
          <span className="entry__contextarrow">→</span>
          <span className="entry__contextname">{route.receiving.name}</span>
          <span className="entry__contextmeta">
            {route.major.label} · {route.major.year_label}
          </span>
        </div>
        <div className="entry__back" onClick={onBack}>
          ← CHANGE ROUTE
        </div>
      </div>
      <div className="entry__main">
        {banner && <ErrorBanner message={banner} onRetry={onRetryBanner} />}
        {localError && (
          <ErrorBanner message={localError} onRetry={() => setLocalError(null)} />
        )}
        <div>
          <h1 className="entry__title">Your courses</h1>
          <p className="entry__sub">
            Add the {route.sending.name} courses you've completed - or paste your transcript.
            Foothold resolves each one against the official course list.
          </p>
        </div>
        <div className="entry__chipwrap">
          <div className="entry__chipbox">
            {chipState.chips.map((chip) => (
              <span key={chip.course_code} className="entry__chip">
                {chip.course_code}
                <span
                  className="entry__chipx"
                  onClick={() => setChipState((state) => removeChip(state, chip.course_code))}
                >
                  ×
                </span>
              </span>
            ))}
            <input
              className="entry__input"
              value={chipState.input}
              onChange={(e) => setChipState((state) => setInput(state, e.target.value))}
              onKeyDown={onKeyDown}
              placeholder="Type a course code - MATH 1A, CIS 22C…"
            />
          </div>
          {sugs.length > 0 && (
            <div className="entry__sugs">
              {sugs.map((hit) => (
                <div key={hit.course_code} className="entry__sug" onClick={() => accept(hit)}>
                  <b>{hit.course_code}</b> <span className="entry__sugtitle">{hit.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="entry__actions">
          <button className="entry__sample" onClick={onSample}>
            Try a sample transcript
          </button>
          <span className="entry__count">{chipState.chips.length} COURSES ADDED</span>
          <div className="entry__cta">
            <FoilButton size="md" disabled={chipState.chips.length === 0} onClick={onEvaluate}>
              See what transfers →
            </FoilButton>
          </div>
        </div>
        <div className="entry__pasteblock">
          <span className="entry__pastelabel">OR PASTE YOUR TRANSCRIPT</span>
          <textarea
            className="entry__paste"
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            placeholder="Paste any transcript text - Foothold picks out the course codes."
          />
          <div className="entry__parsebar">
            <button className="entry__sample entry__parse" onClick={onParse}>
              Parse courses
            </button>
            <span className="entry__parsemsg">{parseMsg}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
