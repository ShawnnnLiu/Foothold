import { useCallback, useState } from "react";

import type { Evaluation } from "./lib/api";
import { createEvaluation, errorText } from "./lib/client";
import { type ChipState, EMPTY_CHIP_STATE, loadSample } from "./lib/courses";
import type { DemoStart } from "./lib/demo";
import type { RouteContext } from "./lib/route";
import Entry from "./screens/Entry";
import Landing from "./screens/Landing";
import Picker from "./screens/Picker";
import Theater from "./screens/Theater";
import Triage from "./screens/Triage";

// The doc-03 app shell: no router, a screen state machine exactly like the
// prototype. Deep links are out of scope for v1; every visit starts at the
// marketing landing page, and every "Check my credits" enters the picker
// (the export's prototype link).
type Screen = "landing" | "picker" | "entry" | "theater" | "triage";

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [route, setRoute] = useState<RouteContext | null>(null);
  const [chipState, setChipState] = useState<ChipState>(EMPTY_CHIP_STATE);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [entryError, setEntryError] = useState<string | null>(null);

  const startRoute = (next: RouteContext) => {
    setChipState((prev) =>
      route && route.sending.assist_id === next.sending.assist_id ? prev : EMPTY_CHIP_STATE,
    );
    setRoute(next);
    setEvaluation(null);
    setEntryError(null);
    setScreen("entry");
  };

  // The demo button's entry: unlike startRoute, the preset chips always
  // replace whatever was typed before, so every roll is a fresh transcript.
  const startDemo = (demo: DemoStart) => {
    setChipState(() => loadSample(demo.chips));
    setRoute(demo.route);
    setEvaluation(null);
    setEntryError(null);
    setScreen("entry");
  };

  const evaluate = useCallback(() => {
    if (!route) {
      return;
    }
    setEntryError(null);
    setEvaluation(null);
    setScreen("theater");
    createEvaluation({
      sending_institution_id: route.sending.assist_id,
      receiving_institution_id: route.receiving.assist_id,
      major_key: route.major.assist_key,
      courses: chipState.chips.map((chip) => ({ course_code: chip.course_code })),
    })
      .then(setEvaluation)
      .catch((e: unknown) => {
        setEntryError(errorText(e));
        setScreen("entry");
      });
  }, [route, chipState]);

  const showTriage = useCallback(() => setScreen("triage"), []);
  const goPicker = () => setScreen("picker");
  const goEntry = () => setScreen("entry");

  if (screen === "picker") {
    return <Picker onStart={startRoute} onDemo={startDemo} />;
  }
  if (screen === "entry" && route) {
    return (
      <Entry
        route={route}
        chipState={chipState}
        setChipState={setChipState}
        banner={entryError}
        onRetryBanner={evaluate}
        onBack={goPicker}
        onEvaluate={evaluate}
      />
    );
  }
  if (screen === "theater") {
    return <Theater evaluation={evaluation} onDone={showTriage} />;
  }
  if (screen === "triage" && route && evaluation) {
    return (
      <Triage
        route={route}
        evaluation={evaluation}
        onEditCourses={goEntry}
        onChangeRoute={goPicker}
      />
    );
  }
  return <Landing onEnter={goPicker} />;
}
