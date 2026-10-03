import { ArrowLeft, CircleAlert, CircleCheck, Code2, Info } from "lucide-react";
import type { AnalysisResponse } from "../types";

type TraceTab = "inspector" | "coverage" | "raw";

interface TraceSummaryProps {
  activeTab: TraceTab;
  analysis: AnalysisResponse;
  onBackToTraces: () => void;
  onTabChange: (tab: TraceTab) => void;
  onToggleFinding: () => void;
  onToggleTrajectory: () => void;
}

function metadataValue(metadata: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = metadata?.[key];
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

export function TraceSummary({
  activeTab,
  analysis,
  onBackToTraces,
  onTabChange,
  onToggleFinding,
  onToggleTrajectory,
}: TraceSummaryProps) {
  const { trace, report } = analysis;
  const title = trace.trace_id ?? "Untitled trace";
  const benchmark = metadataValue(trace.metadata, "benchmark") ?? "Benchmark unknown";
  const agent = trace.agent ?? metadataValue(trace.metadata, "model") ?? "Unknown model";
  const StatusIcon = report.status === "PASS" ? CircleCheck : CircleAlert;

  return (
    <header className="trace-summary" aria-label="Trace summary">
      <button type="button" className="back-link" onClick={onBackToTraces}>
        <ArrowLeft size={14} aria-hidden="true" />
        <span>Traces</span>
      </button>
      <div className="summary-main">
        <div className="summary-title-row">
          <h1>{title}</h1>
          <span className={`status-pill status-${report.status.toLowerCase()}`}>
            <StatusIcon size={13} aria-hidden="true" />
            {report.status}
          </span>
          <details className="trace-info">
            <summary aria-label="Trace Info">
              <Info size={15} aria-hidden="true" />
            </summary>
            <div className="trace-info-popover">
              <h2>Trace Info</h2>
              <dl>
                <div>
                  <dt>Task</dt>
                  <dd>{trace.task ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{agent}</dd>
                </div>
                <div>
                  <dt>Benchmark</dt>
                  <dd>{benchmark}</dd>
                </div>
                <div>
                  <dt>Trace ID</dt>
                  <dd><code>{trace.trace_id ?? "Not available"}</code></dd>
                </div>
              </dl>
            </div>
          </details>
        </div>
        <div className="summary-meta">
          <span>{agent} · {benchmark} · {trace.steps.length} steps</span>
        </div>
      </div>
      <div className="summary-counts">
        <span className="summary-count count-error">
          <strong>{report.error_count}</strong>
          <span>Errors</span>
        </span>
        <span className="summary-count count-warning">
          <strong>{report.warning_count}</strong>
          <span>Warnings</span>
        </span>
      </div>
      <nav className="trace-tabs" aria-label="Trace views">
        <button
          type="button"
          className={activeTab === "inspector" ? "active" : ""}
          onClick={() => onTabChange("inspector")}
        >
          Inspector
        </button>
        <button
          type="button"
          className={activeTab === "raw" ? "active" : ""}
          onClick={() => onTabChange("raw")}
        >
          <Code2 size={14} aria-hidden="true" />
          Raw Trace
        </button>
      </nav>
      <div className="summary-actions">
        <button type="button" className="drawer-toggle trajectory-toggle" onClick={onToggleTrajectory}>
          Trajectory
        </button>
        <button type="button" className="drawer-toggle finding-toggle" onClick={onToggleFinding}>
          Finding
        </button>
      </div>
    </header>
  );
}
