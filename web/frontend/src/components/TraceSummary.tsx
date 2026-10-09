import { ArrowLeft, CircleAlert, CircleCheck, Code2, Info, ShieldCheck } from "lucide-react";
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

function metadataLine(parts: Array<string | null>) {
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
}

function formatCountLabel(count: number, singular: string, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
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
  const benchmark = metadataValue(trace.metadata, "benchmark");
  const agent = trace.agent ?? metadataValue(trace.metadata, "model");
  const headerMetadata = metadataLine([agent, benchmark, `${trace.steps.length} steps`]);
  const StatusIcon = report.status === "PASS" ? CircleCheck : CircleAlert;

  return (
    <header className="trace-summary" aria-label="Trace summary">
      <button type="button" className="back-link" onClick={onBackToTraces}>
        <ArrowLeft size={14} aria-hidden="true" />
        <span>Traces</span>
      </button>
      <div className="summary-main">
        <div className="summary-title-row">
          <h1 title={title}>{title}</h1>
          <span className={`status-pill status-${report.status.toLowerCase()} desktop-status`}>
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
                  <dd>{agent ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Benchmark</dt>
                  <dd>{benchmark ?? "Not available"}</dd>
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
          <span>{headerMetadata}</span>
        </div>
      </div>
      <div className="summary-signal-row">
        <span className={`status-pill status-${report.status.toLowerCase()} mobile-status`}>
          <StatusIcon size={13} aria-hidden="true" />
          {report.status}
        </span>
        <div className="summary-counts">
          <span className="summary-count count-error">
            <strong>{report.error_count}</strong>
            <span>{formatCountLabel(report.error_count, "Error")}</span>
          </span>
          <span className="summary-count count-warning">
            <strong>{report.warning_count}</strong>
            <span>{formatCountLabel(report.warning_count, "Warning")}</span>
          </span>
        </div>
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
          className={activeTab === "coverage" ? "active" : ""}
          onClick={() => onTabChange("coverage")}
        >
          <ShieldCheck size={14} aria-hidden="true" />
          Coverage
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
      {activeTab === "inspector" && (
        <div className="summary-actions">
          <button type="button" className="drawer-toggle trajectory-toggle" onClick={onToggleTrajectory}>
            Trajectory
          </button>
          <button type="button" className="drawer-toggle finding-toggle" onClick={onToggleFinding}>
            Finding
          </button>
        </div>
      )}
    </header>
  );
}
