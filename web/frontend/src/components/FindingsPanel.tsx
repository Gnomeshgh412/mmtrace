import type { Finding } from "../types";

interface FindingsPanelProps {
  findings: Finding[];
  selectedFinding: Finding | null;
  selectedStepId: string | null;
  onSelectFinding: (finding: Finding) => void;
}

function findingKey(finding: Finding) {
  return `${finding.rule_id}:${finding.step_id ?? "trace"}`;
}

function readableValue(value: unknown): string {
  if (value === undefined) return "Not available";
  if (value === null) return "Not available";
  if (Array.isArray(value)) return value.map(readableValue).join(", ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, nestedValue]) => `${key}: ${readableValue(nestedValue)}`)
      .join("; ");
  }
  return String(value);
}

function EvidenceList({ evidence }: { evidence?: Record<string, unknown> | null }) {
  if (!evidence || Object.keys(evidence).length === 0) {
    return <p className="empty-copy">No evidence fields recorded.</p>;
  }

  return (
    <dl className="evidence-grid">
      {Object.entries(evidence).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{readableValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function FindingsPanel({
  findings,
  selectedFinding,
  selectedStepId,
  onSelectFinding,
}: FindingsPanelProps) {
  return (
    <aside className="panel findings-panel" aria-label="Reliability findings">
      <section>
        <div className="panel-heading">
          <h2>Findings</h2>
          <span className="muted">{findings.length} total</span>
        </div>

        {findings.length === 0 ? (
          <div className="empty-state" role="status">
            <h3>No reliability findings</h3>
            <p>
              No deterministic reliability issues were found for the currently
              evaluable rules.
            </p>
            <p>Not every implemented rule may be evaluable from this trace.</p>
          </div>
        ) : (
          <>
            {selectedFinding && (
              <section className="finding-detail selected-finding-detail" aria-label="Selected finding detail">
                <div className="selected-finding-header">
                  <span className={`severity-badge severity-${selectedFinding.severity.toLowerCase()}`}>
                    {selectedFinding.severity}
                  </span>
                  <span className="finding-rule">{selectedFinding.rule_id}</span>
                  <strong>{selectedFinding.title}</strong>
                  <span className="muted">{selectedFinding.step_id ?? "Trace-level"}</span>
                </div>
                <h3>Evidence</h3>
                <EvidenceList evidence={selectedFinding.evidence} />
                <h4>Explanation</h4>
                <p>{selectedFinding.explanation ?? "Not available"}</p>
                <h4>Suggestion</h4>
                <p>{selectedFinding.suggestion ?? "Not available"}</p>
              </section>
            )}

            <section className="all-findings-section" aria-label="All findings">
              <div className="panel-heading compact-heading">
                <h3>All Findings</h3>
                <span className="muted">{findings.length} total</span>
              </div>
              <div className="finding-list">
                {findings.map((finding) => {
                  const selected = selectedFinding
                    ? findingKey(finding) === findingKey(selectedFinding)
                    : false;
                  const relatedToStep = finding.step_id === selectedStepId;

                  return (
                    <button
                      type="button"
                      key={findingKey(finding)}
                      className={`finding-card ${selected ? "selected" : ""} ${
                        relatedToStep ? "related" : ""
                      }`}
                      onClick={() => onSelectFinding(finding)}
                    >
                      <span className={`severity-badge severity-${finding.severity.toLowerCase()}`}>
                        {finding.severity}
                      </span>
                      <span className="finding-rule">{finding.rule_id}</span>
                      <strong>{finding.title}</strong>
                      <span>{finding.step_id ?? "Trace-level"}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          </>
        )}
      </section>
      <section className="coverage-section" aria-label="Rule coverage">
        <div className="panel-heading">
          <h2>Rule Coverage</h2>
        </div>
        <p className="empty-copy">
          Evidence coverage is not included in the current API response.
        </p>
      </section>
    </aside>
  );
}
