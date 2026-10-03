import { useEffect, useMemo, useRef, useState } from "react";
import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react";
import type { Finding, Severity, Step } from "../types";

interface TrajectoryListProps {
  steps: Step[];
  findings: Finding[];
  selectedStepId: string | null;
  onSelectStep: (stepId: string) => void;
}

type StepStatus = "ERROR" | "WARNING" | "Normal";
type StepFilter = "all" | "findings";

function statusForStep(stepId: string, findings: Finding[]): StepStatus {
  const severities = findings
    .filter((finding) => finding.step_id === stepId)
    .map((finding) => finding.severity);

  if (severities.includes("ERROR")) return "ERROR";
  if (severities.includes("WARNING")) return "WARNING";
  return "Normal";
}

function statusClass(status: StepStatus | Severity) {
  return status.toLowerCase();
}

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === "ERROR") {
    return <CircleAlert size={15} aria-hidden="true" />;
  }
  if (status === "WARNING") {
    return <TriangleAlert size={15} aria-hidden="true" />;
  }
  return <CircleCheck size={15} aria-hidden="true" />;
}

export function TrajectoryList({
  steps,
  findings,
  selectedStepId,
  onSelectStep,
}: TrajectoryListProps) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const stepRefs = useRef(new Map<string, HTMLButtonElement>());
  const [filter, setFilter] = useState<StepFilter>("all");
  const findingStepIds = useMemo(
    () => new Set(findings.map((finding) => finding.step_id).filter(Boolean)),
    [findings],
  );
  const findingStepCount = findingStepIds.size;
  const visibleSteps = filter === "findings"
    ? steps.filter((step) => step.step_id && findingStepIds.has(step.step_id))
    : steps;

  useEffect(() => {
    if (!selectedStepId) return;

    const panel = listRef.current;
    const stepButton = stepRefs.current.get(selectedStepId);
    if (!panel || !stepButton) return;

    const panelRect = panel.getBoundingClientRect();
    const stepRect = stepButton.getBoundingClientRect();
    const nextTop =
      panel.scrollTop +
      stepRect.top -
      panelRect.top -
      (panel.clientHeight - stepButton.clientHeight) / 2;

    panel.scrollTo({
      top: Math.max(0, nextTop),
      behavior: "smooth",
    });
  }, [selectedStepId]);

  return (
    <aside className="panel trajectory-panel" aria-label="Trajectory">
      <div className="trajectory-toolbar">
        <div className="panel-heading">
          <div>
            <h2>Steps</h2>
          </div>
          <span className="trajectory-total">{steps.length}</span>
        </div>
        <div className="trajectory-filter-row">
          <div className="segmented-control" aria-label="Trajectory filter">
            <button
              type="button"
              className={filter === "all" ? "active" : ""}
              onClick={() => setFilter("all")}
            >
              All {steps.length}
            </button>
            <button
              type="button"
              className={filter === "findings" ? "active" : ""}
              onClick={() => setFilter("findings")}
            >
              Findings {findingStepCount}
            </button>
          </div>
        </div>
      </div>
      <div ref={listRef} className="step-list-scroll">
        <ol className="step-list">
          {visibleSteps.map((step) => {
            const status = statusForStep(step.step_id, findings);
            const actionType = step.action?.type ?? "No action";
            const selected = step.step_id === selectedStepId;
            const index = steps.findIndex((candidate) => candidate.step_id === step.step_id);

            return (
              <li key={step.step_id}>
                <button
                  type="button"
                  ref={(node) => {
                    if (node) {
                      stepRefs.current.set(step.step_id, node);
                    } else {
                      stepRefs.current.delete(step.step_id);
                    }
                  }}
                  className={`step-button ${selected ? "selected" : ""}`}
                  onClick={() => onSelectStep(step.step_id)}
                  aria-current={selected ? "step" : undefined}
                >
                  <span className={`step-marker marker-${statusClass(status)}`}>
                    <StatusIcon status={status} />
                  </span>
                  <span className="step-index">{index + 1}</span>
                  <span className="step-action">{actionType}</span>
                  {selected && status !== "Normal" && (
                    <span className={`step-status status-text-${statusClass(status)}`}>
                      {status}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
        {visibleSteps.length === 0 && (
          <p className="empty-copy">No steps with findings.</p>
        )}
      </div>
    </aside>
  );
}
