import { useEffect, useRef, useState } from "react";

import ErrorBanner from "../components/ErrorBanner";
import FoilButton from "../components/FoilButton";
import Wordmark from "../components/Wordmark";
import type { InstitutionRow, MajorRow } from "../lib/api";
import { errorText, fetchInstitutions, fetchMajors, searchCourses } from "../lib/client";
import { assembleDemo, DEMO_PRESETS, type DemoStart, pickDemoIndex } from "../lib/demo";
import type { RouteContext } from "../lib/route";

import "./Landing.css";

export default function Landing({
  onStart,
  onDemo,
}: {
  onStart: (route: RouteContext) => void;
  onDemo: (demo: DemoStart) => void;
}) {
  const [ccs, setCcs] = useState<InstitutionRow[]>([]);
  const [targets, setTargets] = useState<InstitutionRow[]>([]);
  const [majors, setMajors] = useState<MajorRow[]>([]);
  const [sendingId, setSendingId] = useState("");
  const [receivingId, setReceivingId] = useState("");
  const [majorKey, setMajorKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const [demoBusy, setDemoBusy] = useState(false);
  const lastDemoRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInstitutions("cc"), fetchInstitutions("target")])
      .then(([cc, target]) => {
        if (!cancelled) {
          setCcs(cc.institutions);
          setTargets(target.institutions);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(errorText(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [retryTick]);

  useEffect(() => {
    setMajors([]);
    setMajorKey("");
    if (!sendingId || !receivingId) {
      return;
    }
    let cancelled = false;
    fetchMajors(Number(sendingId), Number(receivingId))
      .then((body) => {
        if (!cancelled) {
          setMajors(body.majors);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(errorText(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sendingId, receivingId, retryTick]);

  const sending = ccs.find((row) => String(row.assist_id) === sendingId);
  const receiving = targets.find((row) => String(row.assist_id) === receivingId);
  const major = majors.find((row) => row.assist_key === majorKey);
  const yearLabel = majors[0]?.year_label;

  // Math.random is click-handler input (which preset to load), never render
  // state; the chosen preset renders deterministically from there on.
  const runDemo = async () => {
    if (demoBusy || ccs.length === 0 || targets.length === 0) {
      return;
    }
    setDemoBusy(true);
    try {
      const index = pickDemoIndex(DEMO_PRESETS.length, Math.random, lastDemoRef.current);
      const preset = DEMO_PRESETS[index];
      if (!preset) {
        return;
      }
      lastDemoRef.current = index;
      const demo = await assembleDemo(preset, {
        ccs,
        targets,
        fetchMajors,
        search: (institutionId, q) => searchCourses(institutionId, q).then((body) => body.courses),
      });
      if (demo.unresolved.length > 0) {
        setError(
          `Demo preset drifted from the data build - not resolved: ${demo.unresolved.join(", ")}`,
        );
        return;
      }
      setError(null);
      onDemo(demo);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <div className="landing">
      {error && <ErrorBanner message={error} onRetry={() => setRetryTick((t) => t + 1)} />}
      <Wordmark size="lg" frame="slate" />
      <div className="landing__head">
        <h1>Don't lose the credits you already earned.</h1>
        <p>
          Pick your route. Foothold checks every course against the official transfer agreement
          between your two schools - and every verdict cites the exact line it came from.
        </p>
      </div>
      <div className="landing__pickers">
        <div className="landing__pick">
          <span className="landing__label">COMMUNITY COLLEGE</span>
          <select
            className="landing__select landing__select--cc"
            value={sendingId}
            onChange={(e) => setSendingId(e.target.value)}
          >
            <option value="">SELECT A COLLEGE</option>
            {ccs.map((row) => (
              <option key={row.assist_id} value={row.assist_id}>
                {row.name}
              </option>
            ))}
          </select>
        </div>
        <span className="landing__arrow">→</span>
        <div className="landing__pick">
          <span className="landing__label">TARGET UNIVERSITY</span>
          <select
            className="landing__select landing__select--target"
            value={receivingId}
            onChange={(e) => setReceivingId(e.target.value)}
          >
            <option value="">SELECT A UNIVERSITY</option>
            {targets.map((row) => (
              <option key={row.assist_id} value={row.assist_id}>
                {row.name}
              </option>
            ))}
          </select>
        </div>
        <div className="landing__pick">
          <span className="landing__label">MAJOR</span>
          <select
            className="landing__select landing__select--major"
            value={majorKey}
            onChange={(e) => setMajorKey(e.target.value)}
            disabled={majors.length === 0}
          >
            <option value="">
              {sendingId && receivingId ? "SELECT A MAJOR" : "PICK BOTH SCHOOLS FIRST"}
            </option>
            {majors.map((row) => (
              <option key={row.assist_key} value={row.assist_key}>
                {row.label}
              </option>
            ))}
          </select>
        </div>
        <FoilButton
          size="lg"
          disabled={!sending || !receiving || !major}
          onClick={() => sending && receiving && major && onStart({ sending, receiving, major })}
        >
          Check my credits →
        </FoilButton>
      </div>
      <div className="landing__demo">
        <span className="landing__demo-hint">No transcript handy?</span>
        <FoilButton
          size="md"
          finish="rainbow"
          disabled={ccs.length === 0 || targets.length === 0 || demoBusy}
          onClick={runDemo}
          title="Load a real route and real courses mined from the ASSIST agreements"
        >
          {demoBusy ? "Rolling a real route…" : "🎲 Roll a random demo"}
        </FoilButton>
      </div>
      <div className="landing__stats">
        <div className="landing__stat">
          <span className="landing__gao">
            Transfer students lose an average of 43% of their credits
          </span>{" "}
          <span className="landing__gaoref">(GAO-17-574)</span>
        </div>
        <div className="landing__scale">
          Powered by ASSIST.org, California's official transfer database · Every California
          community college on day one
          {yearLabel ? ` · Agreement year ${yearLabel}` : ""}
        </div>
      </div>
    </div>
  );
}
