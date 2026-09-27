import { useMemo, useState } from "react";
import { analyzeTrace, TraceAnalyzeError } from "./api";
import { FindingsPanel } from "./components/FindingsPanel";
import { StepInspector } from "./components/StepInspector";
import { TraceLoader } from "./components/TraceLoader";
import { TraceSummary } from "./components/TraceSummary";
import { TrajectoryList } from "./components/TrajectoryList";
import type { AdapterName, AnalysisResponse, AnalyzeError, Finding } from "./types";

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
    if (finding.step_id) {
      setSelectedStepId(finding.step_id);
    }
  }

  return (
    <div className="app-shell">
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

      {analysis ? (
        <>
          <TraceSummary analysis={analysis} />
          <main className="inspector-layout">
            <TrajectoryList
              findings={analysis.report.findings}
              selectedStepId={selectedStep?.step_id ?? null}
              steps={analysis.trace.steps}
              onSelectStep={(stepId) => {
                setSelectedStepId(stepId);
                setSelectedFindingId(null);
              }}
            />
            <StepInspector
              artifacts={analysis.artifacts}
              resetKey={`${selectedStep?.step_id ?? "none"}:${selectedFindingId ?? ""}`}
              step={selectedStep}
            />
            <FindingsPanel
              findings={analysis.report.findings}
              selectedFinding={selectedFinding}
              selectedStepId={selectedStep?.step_id ?? null}
              onSelectFinding={handleFindingSelect}
            />
          </main>
        </>
      ) : (
        <main className="empty-workspace">
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
