import type { AnalysisResponse } from "../types";

interface TraceSummaryProps {
  analysis: AnalysisResponse;
}

export function TraceSummary({ analysis }: TraceSummaryProps) {
  const { trace, report } = analysis;

  return (
    <header className="trace-summary" aria-label="Trace summary">
      <div className="summary-primary">
        <span className="summary-agent">{trace.agent ?? "Unknown Agent"}</span>
        <span className="summary-separator">·</span>
        <span>{trace.steps.length} Steps</span>
      </div>
      <div className="summary-task">{trace.task ?? "Task not available"}</div>
      <div className="summary-status-group">
        <span className={`status-pill status-${report.status.toLowerCase()}`}>
          {report.status}
        </span>
        <span>{report.error_count} Error</span>
        <span>{report.warning_count} Warning</span>
      </div>
    </header>
  );
}
