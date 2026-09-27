import type { Finding, Severity, Step } from "../types";

interface TrajectoryListProps {
  steps: Step[];
  findings: Finding[];
  selectedStepId: string | null;
  onSelectStep: (stepId: string) => void;
}

type StepStatus = "ERROR" | "WARNING" | "Normal";

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

export function TrajectoryList({
  steps,
  findings,
  selectedStepId,
  onSelectStep,
}: TrajectoryListProps) {
  return (
    <aside className="panel trajectory-panel" aria-label="Trajectory">
      <div className="panel-heading">
        <h2>Trajectory</h2>
      </div>
      <ol className="step-list">
        {steps.map((step, index) => {
          const status = statusForStep(step.step_id, findings);
          const actionType = step.action?.type ?? "No action";
          const selected = step.step_id === selectedStepId;

          return (
            <li key={step.step_id}>
              <button
                type="button"
                className={`step-button ${selected ? "selected" : ""}`}
                onClick={() => onSelectStep(step.step_id)}
                aria-current={selected ? "step" : undefined}
              >
                <span className="step-index">Step {index + 1}</span>
                <span className="step-action">{actionType}</span>
                <span className={`step-status status-text-${statusClass(status)}`}>
                  {status}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
