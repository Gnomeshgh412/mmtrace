import { useEffect, useMemo, useState } from "react";
import { Home, ListTree, Menu, RefreshCw, ShieldCheck, Upload } from "lucide-react";
import { analyzeTrace, getAnalysis, listAnalyses, TraceAnalyzeError } from "./api";
import { FindingsPanel } from "./components/FindingsPanel";
import { StepInspector } from "./components/StepInspector";
import { TraceLoader } from "./components/TraceLoader";
import { TraceSummary } from "./components/TraceSummary";
import { TracesPage } from "./components/TracesPage";
import { TrajectoryList } from "./components/TrajectoryList";
import type {
  AdapterName,
  AnalysisListFilters,
  AnalysisResponse,
  AnalysisSummary,
  AnalyzeError,
  Finding,
} from "./types";

type TraceTab = "inspector" | "coverage" | "raw";
type Route =
  | { view: "import" }
  | { view: "traces" }
  | { analysisId: string; view: "analysis" };

function parseRoute(pathname = window.location.pathname): Route {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] === "traces" && segments[1]) {
    return { view: "analysis", analysisId: decodeURIComponent(segments[1]) };
  }
  if (segments[0] === "traces") {
    return { view: "traces" };
  }
  return { view: "import" };
}

function pathForRoute(route: Route) {
  if (route.view === "analysis") {
    return `/traces/${encodeURIComponent(route.analysisId)}`;
  }
  if (route.view === "traces") return "/traces";
  return "/";
}

function firstStepId(analysis: AnalysisResponse): string | null {
  return analysis.trace.steps[0]?.step_id ?? null;
}

function findingIdentity(finding: Finding): string {
  return `${finding.rule_id}:${finding.step_id ?? "trace"}`;
}

function initialSelection(analysis: AnalysisResponse): {
  findingId: string | null;
  stepId: string | null;
} {
  const screenshotIds = new Set(Object.keys(analysis.artifacts.screenshots ?? {}));
  const findingWithScreenshot = analysis.report.findings.find((finding) => {
    if (!finding.step_id) return false;
    const step = analysis.trace.steps.find((item) => item.step_id === finding.step_id);
    const observationId = step?.observation?.observation_id;
    return Boolean(observationId && screenshotIds.has(observationId));
  });
  const finding = findingWithScreenshot ?? analysis.report.findings[0] ?? null;

  return {
    findingId: finding ? findingIdentity(finding) : null,
    stepId: finding?.step_id ?? firstStepId(analysis),
  };
}

function normalizeError(error: unknown): AnalyzeError {
  if (error instanceof TraceAnalyzeError) {
    return {
      code: error.code,
      message: error.message,
    };
  }

  return {
    code: "INTERNAL_ERROR",
    message: "Unable to analyze trace.",
  };
}

function App() {
  const [route, setRoute] = useState<Route>(() => parseRoute());
  const [adapter, setAdapter] = useState<AdapterName>("generic");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [artifactFile, setArtifactFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailError, setDetailError] = useState<AnalyzeError | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [allAnalyses, setAllAnalyses] = useState<AnalysisSummary[]>([]);
  const [traceFilters, setTraceFilters] = useState<AnalysisListFilters>({});
  const [tracesError, setTracesError] = useState<string | null>(null);
  const [isTracesLoading, setIsTracesLoading] = useState(() => parseRoute().view === "traces");
  const [traceListReloadKey, setTraceListReloadKey] = useState(0);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TraceTab>("inspector");
  const [trajectoryOpen, setTrajectoryOpen] = useState(false);
  const [findingOpen, setFindingOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  function navigate(nextRoute: Route) {
    const nextPath = pathForRoute(nextRoute);
    if (window.location.pathname !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    setRoute(nextRoute);
    setMobileNavOpen(false);
  }

  useEffect(() => {
    function handlePopState() {
      setRoute(parseRoute());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listAnalyses({}, controller.signal)
      .then(setAllAnalyses)
      .catch((nextError: unknown) => {
        if (nextError instanceof DOMException && nextError.name === "AbortError") return;
        setAllAnalyses([]);
      });
    return () => controller.abort();
  }, [traceListReloadKey]);

  useEffect(() => {
    if (route.view !== "traces") return;

    const controller = new AbortController();
    setIsTracesLoading(true);
    const timeout = window.setTimeout(() => {
      setTracesError(null);
      listAnalyses(traceFilters, controller.signal)
        .then((nextAnalyses) => {
          setAnalyses(nextAnalyses);
          setTracesError(null);
        })
        .catch((nextError: unknown) => {
          if (nextError instanceof DOMException && nextError.name === "AbortError") return;
          setTracesError("Couldn’t load traces.");
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setIsTracesLoading(false);
          }
        });
    }, 250);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [route.view, traceFilters, traceListReloadKey]);

  useEffect(() => {
    if (route.view !== "analysis") return;
    if (analysis?.analysis_id === route.analysisId) return;

    const controller = new AbortController();
    setIsDetailLoading(true);
    setDetailError(null);
    setAnalysis(null);
    getAnalysis(route.analysisId, controller.signal)
      .then((nextAnalysis) => {
        const selection = initialSelection(nextAnalysis);
        setAnalysis(nextAnalysis);
        setSelectedStepId(selection.stepId);
        setSelectedFindingId(selection.findingId);
        setActiveTab("inspector");
        setTrajectoryOpen(false);
        setFindingOpen(false);
      })
      .catch((nextError: unknown) => {
        if (nextError instanceof DOMException && nextError.name === "AbortError") return;
        setDetailError(normalizeError(nextError));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsDetailLoading(false);
        }
      });

    return () => controller.abort();
  }, [analysis?.analysis_id, route]);

  const selectedStep = useMemo(
    () =>
      analysis?.trace.steps.find((step) => step.step_id === selectedStepId) ??
      analysis?.trace.steps[0] ??
      null,
    [analysis?.trace.steps, selectedStepId],
  );

  const selectedFinding = useMemo(
    () =>
      analysis?.report.findings.find(
        (finding) => findingIdentity(finding) === selectedFindingId,
      ) ?? null,
    [analysis?.report.findings, selectedFindingId],
  );
  const selectedStepIndex = useMemo(
    () =>
      analysis?.trace.steps.findIndex((step) => step.step_id === selectedStep?.step_id) ??
      -1,
    [analysis?.trace.steps, selectedStep?.step_id],
  );

  async function handleAnalyze() {
    if (!selectedFile) return;

    setIsLoading(true);
    setError(null);
    setAnalysis(null);
    setSelectedStepId(null);
    setSelectedFindingId(null);

    try {
      const nextAnalysis = await analyzeTrace({
        adapter,
        artifactFile,
        file: selectedFile,
      });
      const selection = initialSelection(nextAnalysis);
      setAnalysis(nextAnalysis);
      setSelectedStepId(selection.stepId);
      setSelectedFindingId(selection.findingId);
      setActiveTab("inspector");
      setTrajectoryOpen(false);
      setFindingOpen(false);
      setTraceListReloadKey((key) => key + 1);
      navigate({ view: "analysis", analysisId: nextAnalysis.analysis_id });
    } catch (nextError) {
      setError(normalizeError(nextError));
    } finally {
      setIsLoading(false);
    }
  }

  function handleFileChange(file: File | null) {
    setSelectedFile(file);
    setError(null);
  }

  function handleFindingSelect(finding: Finding) {
    setSelectedFindingId(findingIdentity(finding));
    setActiveTab("inspector");
    setFindingOpen(false);
    if (finding.step_id) {
      setSelectedStepId(finding.step_id);
    }
  }

  function handleStepSelect(stepId: string) {
    setSelectedStepId(stepId);
    setSelectedFindingId(null);
    setTrajectoryOpen(false);
  }

  function retryDetail() {
    if (route.view !== "analysis") return;
    const current = route.analysisId;
    setAnalysis(null);
    setDetailError(null);
    setRoute({ view: "analysis", analysisId: current });
  }

  const workspaceMode = route.view !== "import";
  const currentPageLabel = route.view === "import" ? "Import Trace" : "Traces";
  const adapterOptions = useMemo(() => {
    const values = new Set(["generic", "browser-use", "osworld", "holo4"]);
    for (const item of allAnalyses) {
      if (item.adapter) values.add(item.adapter);
    }
    return Array.from(values);
  }, [allAnalyses]);

  return (
    <div className={`app-shell ${workspaceMode ? "workspace-mode" : ""}`}>
      <aside className="global-sidebar" aria-label="MMTrace navigation">
        <div className="brand-block">
          <span className="brand-mark">MM</span>
          <strong>MMTrace</strong>
        </div>
        <span className="mobile-current-page">{currentPageLabel}</span>
        <button
          type="button"
          className="mobile-menu-button"
          aria-label="Open navigation"
          aria-expanded={mobileNavOpen}
          onClick={() => setMobileNavOpen((open) => !open)}
        >
          <Menu size={18} aria-hidden="true" />
        </button>
        <nav className="global-nav" aria-label="Primary">
          <button type="button" disabled title="Overview" aria-label="Overview">
            <Home className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Overview</span>
          </button>
          <button
            type="button"
            className={route.view === "traces" || route.view === "analysis" ? "active" : ""}
            title="Traces"
            aria-label="Traces"
            onClick={() => navigate({ view: "traces" })}
          >
            <ListTree className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Traces</span>
          </button>
          <button type="button" disabled title="Rules" aria-label="Rules">
            <ShieldCheck className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Rules</span>
          </button>
          <button
            type="button"
            className={`import-nav ${route.view === "import" ? "active" : ""}`}
            title="Import Trace"
            aria-label="Import Trace"
            onClick={() => navigate({ view: "import" })}
          >
            <Upload className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Import Trace</span>
          </button>
        </nav>
        {mobileNavOpen && (
          <>
            <button
              type="button"
              className="mobile-nav-backdrop"
              aria-label="Close navigation"
              onClick={() => setMobileNavOpen(false)}
            />
            <nav className="mobile-nav-popover" aria-label="Mobile primary">
              <button type="button" disabled title="Overview" aria-label="Overview">
                <Home className="nav-icon" size={18} aria-hidden="true" />
                <span className="nav-label">Overview</span>
              </button>
              <button
                type="button"
                className={route.view === "traces" || route.view === "analysis" ? "active" : ""}
                title="Traces"
                aria-label="Traces"
                onClick={() => navigate({ view: "traces" })}
              >
                <ListTree className="nav-icon" size={18} aria-hidden="true" />
                <span className="nav-label">Traces</span>
              </button>
              <button type="button" disabled title="Rules" aria-label="Rules">
                <ShieldCheck className="nav-icon" size={18} aria-hidden="true" />
                <span className="nav-label">Rules</span>
              </button>
              <button
                type="button"
                className={`import-nav ${route.view === "import" ? "active" : ""}`}
                title="Import Trace"
                aria-label="Import Trace"
                onClick={() => navigate({ view: "import" })}
              >
                <Upload className="nav-icon" size={18} aria-hidden="true" />
                <span className="nav-label">Import Trace</span>
              </button>
            </nav>
          </>
        )}
        <span className="sidebar-version">
          <span className="version-full">v0.2 dev</span>
          <span className="version-compact">v0.2</span>
        </span>
      </aside>

      {route.view === "import" ? (
        <main className="import-workspace workspace-shell" aria-label="Import trace">
          <section className="import-panel">
            <span className="eyebrow">Import Trace</span>
            <h1>Analyze an existing trace</h1>
            <p>
              Select an adapter, upload a trace, and optionally attach screenshot artifacts.
            </p>
            <TraceLoader
              adapter={adapter}
              artifactFile={artifactFile}
              error={error}
              isLoading={isLoading}
              selectedFile={selectedFile}
              onAdapterChange={setAdapter}
              onArtifactFileChange={(file) => {
                setArtifactFile(file);
                setError(null);
              }}
              onFileChange={handleFileChange}
              onAnalyze={handleAnalyze}
            />
          </section>
        </main>
      ) : route.view === "traces" ? (
        <TracesPage
          adapterOptions={adapterOptions}
          analyses={analyses}
          error={tracesError}
          filters={traceFilters}
          hasAnyAnalyses={allAnalyses.length > 0}
          isLoading={isTracesLoading}
          onClearFilters={() => setTraceFilters({})}
          onFilterChange={setTraceFilters}
          onImportTrace={() => navigate({ view: "import" })}
          onOpenAnalysis={(analysisId) => navigate({ view: "analysis", analysisId })}
          onRetry={() => setTraceListReloadKey((key) => key + 1)}
        />
      ) : route.view === "analysis" && analysis ? (
        <div className="workspace-shell">
          <TraceSummary
            activeTab={activeTab}
            analysis={analysis}
            onBackToTraces={() => navigate({ view: "traces" })}
            onTabChange={setActiveTab}
            onToggleFinding={() => setFindingOpen((open) => !open)}
            onToggleTrajectory={() => setTrajectoryOpen((open) => !open)}
          />
          {activeTab === "inspector" && (
          <main className="inspector-layout">
            <TrajectoryList
              findings={analysis.report.findings}
              selectedStepId={selectedStep?.step_id ?? null}
              steps={analysis.trace.steps}
              onSelectStep={handleStepSelect}
            />
            <StepInspector
              artifacts={analysis.artifacts}
              resetKey={`${selectedStep?.step_id ?? "none"}:${selectedFindingId ?? ""}`}
              selectedFinding={selectedFinding}
              step={selectedStep}
              stepIndex={selectedStepIndex < 0 ? 0 : selectedStepIndex}
              totalSteps={analysis.trace.steps.length}
            />
            <FindingsPanel
              findings={analysis.report.findings}
              selectedFinding={selectedFinding}
              selectedStepId={selectedStep?.step_id ?? null}
              onSelectFinding={handleFindingSelect}
            />
          </main>
          )}
          {activeTab === "coverage" && (
            <main className="placeholder-view">
              <section className="empty-state" role="status">
                <h2>Coverage</h2>
                <p>Coverage data is not included in the current API response.</p>
              </section>
            </main>
          )}
          {activeTab === "raw" && (
            <main className="raw-trace-view">
              <pre className="raw-block">{JSON.stringify(analysis.trace, null, 2)}</pre>
            </main>
          )}
          {(trajectoryOpen || findingOpen) && (
            <button
              type="button"
              className="drawer-backdrop"
              aria-label="Close drawer"
              onClick={() => {
                setTrajectoryOpen(false);
                setFindingOpen(false);
              }}
            />
          )}
          <div className={`mobile-drawer trajectory-drawer ${trajectoryOpen ? "open" : ""}`}>
            <TrajectoryList
              findings={analysis.report.findings}
              selectedStepId={selectedStep?.step_id ?? null}
              steps={analysis.trace.steps}
              onSelectStep={handleStepSelect}
            />
          </div>
          <div className={`mobile-drawer finding-drawer ${findingOpen ? "open" : ""}`}>
            <FindingsPanel
              findings={analysis.report.findings}
              onClose={() => setFindingOpen(false)}
              selectedFinding={selectedFinding}
              selectedStepId={selectedStep?.step_id ?? null}
              onSelectFinding={handleFindingSelect}
            />
          </div>
        </div>
      ) : route.view === "analysis" ? (
        <main className="detail-state-workspace workspace-shell" aria-label="Trace loading">
          <section className="detail-state-panel" role={detailError ? "alert" : "status"}>
            {isDetailLoading || !detailError ? (
              <>
                <h1>Loading trace...</h1>
                <p>Opening the persisted analysis snapshot.</p>
              </>
            ) : detailError?.code === "INVALID_INPUT" ? (
              <>
                <h1>Trace not found</h1>
                <p>This persisted analysis could not be found.</p>
                <button
                  type="button"
                  className="secondary-action"
                  onClick={() => navigate({ view: "traces" })}
                >
                  Back to Traces
                </button>
              </>
            ) : (
              <>
                <h1>Couldn’t open this trace.</h1>
                <p>The persisted analysis snapshot could not be loaded.</p>
                <div className="detail-state-actions">
                  <button
                    type="button"
                    className="secondary-action"
                    onClick={() => navigate({ view: "traces" })}
                  >
                    Back to Traces
                  </button>
                  <button type="button" className="secondary-action" onClick={retryDetail}>
                    <RefreshCw size={14} aria-hidden="true" />
                    Retry
                  </button>
                </div>
              </>
            )}
          </section>
        </main>
      ) : (
        <main className="empty-workspace workspace-shell">
          <section className="empty-state initial-empty-state" aria-label="Empty trace">
            <h1>Open a trace to inspect multimodal agent reliability.</h1>
            <p>
              Select an adapter and upload a JSON trace to run the existing MMTrace
              checks through the FastAPI backend.
            </p>
          </section>
        </main>
      )}
    </div>
  );
}

export default App;
