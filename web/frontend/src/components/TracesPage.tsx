import {
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ListTree,
  RefreshCw,
  Search,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import type { KeyboardEvent } from "react";
import type { AnalysisListFilters, AnalysisSummary, ReportStatus } from "../types";

interface TracesPageProps {
  adapterOptions: string[];
  analyses: AnalysisSummary[];
  filters: AnalysisListFilters;
  hasAnyAnalyses: boolean;
  isLoading: boolean;
  error: string | null;
  onClearFilters: () => void;
  onFilterChange: (filters: AnalysisListFilters) => void;
  onImportTrace: () => void;
  onOpenAnalysis: (analysisId: string) => void;
  onRetry: () => void;
}

function statusLabel(status: ReportStatus) {
  const StatusIcon = status === "PASS" ? CircleCheck : CircleAlert;
  return (
    <span className={`trace-status status-${status.toLowerCase()}`}>
      <StatusIcon size={13} aria-hidden="true" />
      {status}
    </span>
  );
}

function plural(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

function findingsLabel(analysis: AnalysisSummary) {
  if (analysis.finding_count === 0) {
    return <span className="findings-none">No findings</span>;
  }

  return (
    <span className="findings-stack">
      {analysis.error_count > 0 && (
        <span className="findings-error">{plural(analysis.error_count, "Error")}</span>
      )}
      {analysis.warning_count > 0 && (
        <span className="findings-warning">{plural(analysis.warning_count, "Warning")}</span>
      )}
    </span>
  );
}

function adapterLabel(adapter: string) {
  if (adapter === "browser-use") return "Browser Use";
  if (adapter === "osworld") return "OSWorld";
  if (adapter === "holo4") return "Holo4";
  if (adapter === "generic") return "Generic";
  return adapter;
}

function metadataParts(analysis: AnalysisSummary) {
  const parts: string[] = [];
  if (analysis.model) parts.push(analysis.model);
  if (analysis.benchmark) parts.push(analysis.benchmark);

  const adapter = adapterLabel(analysis.adapter);
  const hasAdapterInExistingPart = parts.some((part) =>
    part.toLowerCase().includes(adapter.toLowerCase()),
  );
  if (!hasAdapterInExistingPart) {
    parts.push(adapter);
  }

  parts.push(plural(analysis.step_count, "step"));
  return parts;
}

function TraceRow({
  analysis,
  onOpenAnalysis,
}: {
  analysis: AnalysisSummary;
  onOpenAnalysis: (analysisId: string) => void;
}) {
  const title = analysis.trace_id || analysis.analysis_id;

  function open() {
    onOpenAnalysis(analysis.analysis_id);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  }

  return (
    <div
      className="trace-row"
      role="button"
      tabIndex={0}
      aria-label={`Open trace ${title}`}
      onClick={open}
      onKeyDown={handleKeyDown}
    >
      <div className="trace-cell trace-main-cell">
        <strong title={title}>{title}</strong>
        {analysis.task && <p>{analysis.task}</p>}
        <span>{metadataParts(analysis).join(" · ")}</span>
      </div>
      <div className="trace-cell trace-status-cell">{statusLabel(analysis.status)}</div>
      <div className="trace-cell trace-findings-cell">{findingsLabel(analysis)}</div>
      <div className="trace-cell trace-rules-cell">
        {analysis.rule_hits.length > 0 ? (
          <span className="rule-hit-list">
            {analysis.rule_hits.map((hit) => (
              <span className="rule-hit-token" key={`${hit.rule_id}:${hit.severity}`}>
                {hit.rule_id}
                {hit.count > 1 && <span>×{hit.count}</span>}
              </span>
            ))}
          </span>
        ) : (
          <span className="rule-hit-empty">—</span>
        )}
      </div>
      <ChevronRight className="trace-row-chevron" size={16} aria-hidden="true" />
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="trace-table-body" aria-label="Loading traces">
      {[0, 1, 2, 3].map((row) => (
        <div className="trace-row trace-row-skeleton" key={row}>
          <span />
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  filtered,
  onClearFilters,
  onImportTrace,
}: {
  filtered: boolean;
  onClearFilters: () => void;
  onImportTrace: () => void;
}) {
  return (
    <section className="traces-empty-state" aria-live="polite">
      <ListTree size={22} aria-hidden="true" />
      <h2>{filtered ? "No matching traces" : "No traces yet"}</h2>
      <p>
        {filtered
          ? "Try adjusting your search or filters."
          : "Import an agent trajectory to run your first reliability check."}
      </p>
      <button
        type="button"
        className={filtered ? "secondary-action" : "primary-action"}
        onClick={filtered ? onClearFilters : onImportTrace}
      >
        {filtered ? "Clear filters" : "Import Trace"}
      </button>
    </section>
  );
}

export function TracesPage({
  adapterOptions,
  analyses,
  filters,
  hasAnyAnalyses,
  isLoading,
  error,
  onClearFilters,
  onFilterChange,
  onImportTrace,
  onOpenAnalysis,
  onRetry,
}: TracesPageProps) {
  const hasFilters = Boolean(
    filters.search?.trim() || filters.status || filters.adapter || filters.findings,
  );

  return (
    <main className="traces-workspace workspace-shell" aria-label="Traces">
      <header className="traces-header">
        <div>
          <h1>Traces</h1>
          <p>Browse and inspect analyzed agent trajectories</p>
        </div>
        <button type="button" className="primary-action" onClick={onImportTrace}>
          <Upload size={15} aria-hidden="true" />
          Import Trace
        </button>
      </header>

      <section className="trace-filter-bar" aria-label="Trace filters">
        <label className="trace-search-field">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Search traces</span>
          <input
            type="search"
            placeholder="Search traces..."
            value={filters.search ?? ""}
            onChange={(event) =>
              onFilterChange({ ...filters, search: event.currentTarget.value })
            }
          />
          {filters.search && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => onFilterChange({ ...filters, search: "" })}
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </label>
        <label className="filter-select">
          <span>Status</span>
          <select
            value={filters.status ?? ""}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                status: event.currentTarget.value as ReportStatus | "",
              })
            }
          >
            <option value="">All</option>
            <option value="PASS">PASS</option>
            <option value="FAIL">FAIL</option>
          </select>
        </label>
        <label className="filter-select">
          <span>Adapter</span>
          <select
            value={filters.adapter ?? ""}
            onChange={(event) =>
              onFilterChange({ ...filters, adapter: event.currentTarget.value })
            }
          >
            <option value="">All</option>
            {adapterOptions.map((adapter) => (
              <option key={adapter} value={adapter}>
                {adapterLabel(adapter)}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-select">
          <span>Findings</span>
          <select
            value={filters.findings ?? ""}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                findings: event.currentTarget.value as AnalysisListFilters["findings"],
              })
            }
          >
            <option value="">All</option>
            <option value="errors">Has Errors</option>
            <option value="warnings">Has Warnings</option>
            <option value="none">No Findings</option>
          </select>
        </label>
      </section>
      <div className="trace-result-meta" aria-live="polite">
        {plural(analyses.length, "trace")}
      </div>

      <section className="trace-table-panel" aria-label="Analyzed traces">
        <div className="trace-table-head" aria-hidden="true">
          <span>Trace</span>
          <span>Status</span>
          <span>Findings</span>
          <span>Rule Hits</span>
        </div>

        {isLoading ? (
          <SkeletonRows />
        ) : error ? (
          <section className="traces-error-state" role="alert">
            <TriangleAlert size={18} aria-hidden="true" />
            <span>Couldn’t load traces.</span>
            <button type="button" className="secondary-action" onClick={onRetry}>
              <RefreshCw size={14} aria-hidden="true" />
              Retry
            </button>
          </section>
        ) : analyses.length === 0 ? (
          <EmptyState
            filtered={hasAnyAnalyses && hasFilters}
            onClearFilters={onClearFilters}
            onImportTrace={onImportTrace}
          />
        ) : (
          <div className="trace-table-body">
            {analyses.map((analysis) => (
              <TraceRow
                analysis={analysis}
                key={analysis.analysis_id}
                onOpenAnalysis={onOpenAnalysis}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
