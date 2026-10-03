import { useState } from "react";
import { ChevronLeft, ChevronRight, CircleAlert, TriangleAlert, X } from "lucide-react";
import type { Finding } from "../types";

interface FindingsPanelProps {
  findings: Finding[];
  selectedFinding: Finding | null;
  selectedStepId: string | null;
  onClose?: () => void;
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

const ERROR_PREVIEW_LIMIT = 240;

function lastExceptionLine(value: string): string | null {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of [...lines].reverse()) {
    if (/\b(?:[A-Za-z]+Error|[A-Za-z]+Exception):/.test(line)) {
      return line;
    }
  }

  return null;
}

function errorPreview(value: string): string {
  if (value.length <= ERROR_PREVIEW_LIMIT) return value;

  const receiptIndex = value.indexOf("[Execution receipt]");
  const previewSource =
    receiptIndex > 0 ? value.slice(0, receiptIndex).trimEnd() : value;
  if (previewSource.length <= ERROR_PREVIEW_LIMIT) return previewSource;

  const head = previewSource.slice(0, ERROR_PREVIEW_LIMIT).trimEnd();
  const exceptionLine = lastExceptionLine(value);
  if (exceptionLine && !head.includes(exceptionLine)) {
    return `${head}\n...\n${exceptionLine}`;
  }

  return `${head}\n...`;
}

function EvidenceValue({
  evidenceKey,
  value,
}: {
  evidenceKey: string;
  value: unknown;
}) {
  const readable = readableValue(value);
  const isLongError = evidenceKey === "error" && readable.length > ERROR_PREVIEW_LIMIT;
  const [expanded, setExpanded] = useState(false);

  if (!isLongError) {
    return <span className="evidence-value">{readable}</span>;
  }

  return (
    <div className="evidence-value evidence-error">
      <span className="evidence-error-text">
        {expanded ? readable : errorPreview(readable)}
      </span>
      <button
        type="button"
        className="evidence-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Show less" : "Show full error"}
      </button>
    </div>
  );
}

function keyEvidence(finding: Finding): Array<[string, unknown]> {
  const evidence = finding.evidence;
  if (!evidence) return [];

  return ["execution_status", "action_type"]
    .filter((key) => Object.prototype.hasOwnProperty.call(evidence, key))
    .map((key) => [key, evidence[key]]);
}

function findingError(finding: Finding): unknown {
  return finding.evidence && Object.prototype.hasOwnProperty.call(finding.evidence, "error")
    ? finding.evidence.error
    : undefined;
}

function categoryForFinding(finding: Finding): string {
  if (finding.rule_id === "MMTRACE007") return "Execution";
  return finding.rule_id;
}

function SeverityIcon({ severity }: { severity: Finding["severity"] }) {
  if (severity === "WARNING") {
    return <TriangleAlert size={13} aria-hidden="true" />;
  }
  return <CircleAlert size={13} aria-hidden="true" />;
}

export function FindingsPanel({
  findings,
  onClose,
  selectedFinding,
  selectedStepId,
  onSelectFinding,
}: FindingsPanelProps) {
  const selected =
    selectedFinding ??
    findings.find((finding) => finding.step_id === selectedStepId) ??
    findings[0] ??
    null;
  const selectedIndex = selected
    ? findings.findIndex((finding) => findingKey(finding) === findingKey(selected))
    : -1;
  const previousFinding = selectedIndex > 0 ? findings[selectedIndex - 1] : null;
  const cyclicPrevious =
    findings.length > 0
      ? previousFinding ?? findings[findings.length - 1]
      : null;
  const cyclicNext =
    findings.length > 0
      ? findings[(selectedIndex + 1 + findings.length) % findings.length]
      : null;

  return (
    <aside className="panel findings-panel" aria-label="Reliability findings">
      <section>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Finding</span>
            <h2>Current Finding</h2>
          </div>
          <div className="finding-heading-actions">
            {selectedIndex >= 0 && (
              <span className="finding-position">{selectedIndex + 1} / {findings.length}</span>
            )}
            {onClose && (
              <button
                type="button"
                className="finding-close-button"
                aria-label="Close finding"
                onClick={onClose}
              >
                <X size={17} aria-hidden="true" />
              </button>
            )}
          </div>
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
            {selected && (
              <section className="finding-detail selected-finding-detail" aria-label="Selected finding detail">
                <div className="selected-finding-header">
                  <span className={`severity-badge severity-${selected.severity.toLowerCase()}`}>
                    <SeverityIcon severity={selected.severity} />
                    {selected.severity}
                  </span>
                  <code className="finding-rule">{selected.rule_id}</code>
                  <strong>{selected.title}</strong>
                  <span className="muted">{selected.step_id ?? "Trace-level"}</span>
                </div>
                <p>{selected.explanation ?? "Not available"}</p>
                <dl className="finding-meta">
                  <div>
                    <dt>category</dt>
                    <dd>{categoryForFinding(selected)}</dd>
                  </div>
                  <div>
                    <dt>step</dt>
                    <dd><code>{selected.step_id ?? "trace"}</code></dd>
                  </div>
                </dl>
                {keyEvidence(selected).length > 0 && (
                  <>
                    <h3>Evidence</h3>
                    <dl className="evidence-grid key-evidence">
                      {keyEvidence(selected).map(([key, value]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>
                            <EvidenceValue evidenceKey={key} value={value} />
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
                {findingError(selected) !== undefined && (
                  <section className="finding-error-block" aria-label="Finding error">
                    <h3>Error</h3>
                    <EvidenceValue evidenceKey="error" value={findingError(selected)} />
                  </section>
                )}
                {selected.suggestion && (
                  <p className="secondary-note">
                    <strong>Suggested inspection</strong>
                    <span>{selected.suggestion}</span>
                  </p>
                )}
                <div className="finding-nav" aria-label="Finding navigation">
                  <button
                    type="button"
                    disabled={findings.length < 2}
                    onClick={() => cyclicPrevious && onSelectFinding(cyclicPrevious)}
                  >
                    <ChevronLeft size={14} aria-hidden="true" />
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={findings.length < 2}
                    onClick={() => cyclicNext && onSelectFinding(cyclicNext)}
                  >
                    Next
                    <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </div>
              </section>
            )}
          </>
        )}
      </section>
    </aside>
  );
}
