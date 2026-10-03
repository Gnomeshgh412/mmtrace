import { useMemo, useState } from "react";
import { Home, ListTree, ShieldCheck, Upload } from "lucide-react";
import { analyzeTrace, TraceAnalyzeError } from "./api";
import { FindingsPanel } from "./components/FindingsPanel";
import { StepInspector } from "./components/StepInspector";
import { TraceLoader } from "./components/TraceLoader";
import { TraceSummary } from "./components/TraceSummary";
import { TrajectoryList } from "./components/TrajectoryList";
import type { AdapterName, AnalysisResponse, AnalyzeError, Finding } from "./types";

type TraceTab = "inspector" | "coverage" | "raw";
type AppView = "import" | "inspector";

function firstStepId(analysis: AnalysisResponse): string | null {
  return analysis.trace.steps[0]?.step_id ?? null;
}

function findingIdentity(finding: Finding): string {
  return `${finding.rule_id}:${finding.step_id ?? "trace"}`;
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
  const [adapter, setAdapter] = useState<AdapterName>("generic");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [artifactFile, setArtifactFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TraceTab>("inspector");
  const [appView, setAppView] = useState<AppView>("import");
  const [trajectoryOpen, setTrajectoryOpen] = useState(false);
  const [findingOpen, setFindingOpen] = useState(false);

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
      setAnalysis(nextAnalysis);
      setSelectedStepId(firstStepId(nextAnalysis));
      setSelectedFindingId(null);
      setActiveTab("inspector");
      setAppView("inspector");
      setTrajectoryOpen(false);
      setFindingOpen(false);
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

  const workspaceMode = appView === "inspector" && analysis;

  return (
    <div className={`app-shell ${workspaceMode ? "workspace-mode" : ""}`}>
      <aside className="global-sidebar" aria-label="MMTrace navigation">
        <div className="brand-block">
          <span className="brand-mark">MM</span>
          <strong>MMTrace</strong>
        </div>
        <nav className="global-nav" aria-label="Primary">
          <button type="button" disabled title="Overview" aria-label="Overview">
            <Home className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Overview</span>
          </button>
          <button
            type="button"
            className={appView === "inspector" ? "active" : ""}
            disabled={!analysis}
            title="Traces"
            aria-label="Traces"
            onClick={() => setAppView("inspector")}
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
            className={`import-nav ${appView === "import" ? "active" : ""}`}
            title="Import Trace"
            aria-label="Import Trace"
            onClick={() => setAppView("import")}
          >
            <Upload className="nav-icon" size={18} aria-hidden="true" />
            <span className="nav-label">Import Trace</span>
          </button>
        </nav>
        <span className="sidebar-version">
          <span className="version-full">v0.2 dev</span>
          <span className="version-compact">v0.2</span>
        </span>
      </aside>

      {appView === "import" ? (
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
      ) : analysis ? (
        <div className="workspace-shell">
          <TraceSummary
            activeTab={activeTab}
            analysis={analysis}
            onBackToTraces={() => setAppView("import")}
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
