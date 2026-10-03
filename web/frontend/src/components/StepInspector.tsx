import { useEffect, useMemo, useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  CircleMinus,
  Columns2,
  Cpu,
  Image,
  Images,
  MessageSquareText,
  MousePointer2,
  ScanEye,
  Terminal,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Artifacts, Finding, Observation, Step } from "../types";

interface StepInspectorProps {
  artifacts: Artifacts;
  resetKey: string;
  selectedFinding: Finding | null;
  step: Step | null;
  stepIndex: number;
  totalSteps: number;
}

function valueOrMissing(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type ScreenshotSlot = "before" | "after";
type EvidenceStageId = "observation" | "model-context" | "action" | "execution" | "post-state";
type EvidenceStageState = "available" | "failed" | "unavailable";
const ERROR_PREVIEW_LIMIT = 260;

interface ScreenshotCandidate {
  label: "Before" | "After";
  observation?: Observation | null;
  slot: ScreenshotSlot;
  url?: string;
}

function dimensions(observation?: Observation | null): string {
  if (!observation?.width || !observation.height) return "Not available";
  return `${observation.width} × ${observation.height}`;
}

function conciseDimensions(observation?: Observation | null): string | null {
  if (!observation?.width || !observation.height) return null;
  return `${observation.width} × ${observation.height}`;
}

function viewportDimensions(observation?: Observation | null): string {
  if (!observation?.viewport_width || !observation.viewport_height) {
    return "Not available";
  }
  return `${observation.viewport_width} × ${observation.viewport_height}`;
}

function aspectRatio(observation?: Observation | null): string | undefined {
  if (!observation?.width || !observation.height) return undefined;
  return `${observation.width} / ${observation.height}`;
}

function screenshotCaption(candidate?: ScreenshotCandidate): string {
  if (!candidate?.observation) return "No screenshot metadata";
  const filename =
    candidate.observation.image_path?.split(/[\\/]/).pop() ??
    "No image path recorded";
  const size = conciseDimensions(candidate.observation);
  return size ? `${filename} · ${size}` : filename;
}

function defaultSlot(candidates: ScreenshotCandidate[]): ScreenshotSlot {
  const before = candidates.find((candidate) => candidate.slot === "before");
  if (before?.url) return "before";
  const after = candidates.find((candidate) => candidate.slot === "after");
  if (after?.url) return "after";
  if (before?.observation) return "before";
  if (after?.observation) return "after";
  return "before";
}

function hasObjectData(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  return Object.values(value as Record<string, unknown>).some((item) => {
    if (Array.isArray(item)) return item.length > 0;
    if (item && typeof item === "object") return Object.keys(item).length > 0;
    return item !== null && item !== undefined && item !== "";
  });
}

function evidenceState(stage: EvidenceStageId, step: Step, artifacts: Artifacts): EvidenceStageState {
  if (stage === "observation") {
    if (!step.observation) return "unavailable";
    if (
      step.observation.observation_id &&
      step.observation.image_path &&
      !artifacts.screenshots[step.observation.observation_id]
    ) {
      return "failed";
    }
    return "available";
  }

  if (stage === "model-context") return hasObjectData(step.model_input) ? "available" : "unavailable";
  if (stage === "action") return hasObjectData(step.action) ? "available" : "unavailable";

  if (stage === "execution") {
    if (!hasObjectData(step.execution)) return "unavailable";
    return step.execution?.status === "failed" || Boolean(step.execution?.error) ? "failed" : "available";
  }

  if (!hasObjectData(step.post_state)) return "unavailable";
  if (
    step.post_state?.observation?.observation_id &&
    step.post_state.observation.image_path &&
    !artifacts.screenshots[step.post_state.observation.observation_id]
  ) {
    return "failed";
  }
  return "available";
}

const STAGES: Array<{ id: EvidenceStageId; label: string; Icon: LucideIcon }> = [
  { id: "observation", label: "Observation", Icon: Image },
  { id: "model-context", label: "Model Context", Icon: MessageSquareText },
  { id: "action", label: "Action", Icon: MousePointer2 },
  { id: "execution", label: "Execution", Icon: Cpu },
  { id: "post-state", label: "Post-State", Icon: ScanEye },
];

function StageStatusIcon({ state }: { state: EvidenceStageState }) {
  if (state === "available") {
    return <CircleCheck size={14} aria-hidden="true" />;
  }
  if (state === "failed") {
    return <CircleAlert size={14} aria-hidden="true" />;
  }
  return <CircleMinus size={14} aria-hidden="true" />;
}

function defaultStage(step: Step, selectedFinding: Finding | null): EvidenceStageId {
  if (selectedFinding?.rule_id === "MMTRACE007") return "execution";
  if (hasObjectData(step.action)) return "action";
  if (hasObjectData(step.post_state)) return "post-state";
  if (hasObjectData(step.execution)) return "execution";
  return "observation";
}

function ScreenshotViewer({
  artifacts,
  resetKey,
  step,
  stepIndex,
  totalSteps,
}: {
  artifacts: Artifacts;
  resetKey: string;
  step: Step;
  stepIndex: number;
  totalSteps: number;
}) {
  const candidates = useMemo<ScreenshotCandidate[]>(
    () => [
      {
        label: "Before",
        observation: step.observation,
        slot: "before",
        url: step.observation?.observation_id
          ? artifacts.screenshots[step.observation.observation_id]
          : undefined,
      },
      {
        label: "After",
        observation: step.post_state?.observation,
        slot: "after",
        url: step.post_state?.observation?.observation_id
          ? artifacts.screenshots[step.post_state.observation.observation_id]
          : undefined,
      },
    ],
    [artifacts.screenshots, step],
  );
  const [activeSlot, setActiveSlot] = useState<ScreenshotSlot>(defaultSlot(candidates));

  useEffect(() => {
    setActiveSlot(defaultSlot(candidates));
  }, [candidates, resetKey]);

  const visibleCandidates = candidates.filter(
    (candidate) => candidate.url || candidate.observation,
  );
  const active =
    candidates.find((candidate) => candidate.slot === activeSlot) ?? candidates[0];
  const hasMultipleScreenshots = candidates.filter((candidate) => candidate.url).length > 1;

  return (
    <section className="screenshot-section" aria-label="Screenshot">
      <div className="screenshot-heading">
        <div>
          <span className="eyebrow">Evidence</span>
          <h2>Step {stepIndex + 1} of {totalSteps}</h2>
        </div>
        <div className="screenshot-tabs" aria-label="Screenshot view">
          {candidates
            .filter((candidate) => candidate.url || candidate.observation)
            .map((candidate) => (
              <button
                key={candidate.slot}
                type="button"
                className={activeSlot === candidate.slot ? "active" : ""}
                disabled={!candidate.url}
                onClick={() => setActiveSlot(candidate.slot)}
              >
                {candidate.slot === "before" ? (
                  <Image size={14} aria-hidden="true" />
                ) : (
                  <Images size={14} aria-hidden="true" />
                )}
                {candidate.label}
              </button>
            ))}
          {hasMultipleScreenshots && (
            <button type="button" disabled>
              <Columns2 size={14} aria-hidden="true" />
              Compare
            </button>
          )}
        </div>
      </div>

      {active?.url ? (
        <figure
          className="screenshot-viewer"
          style={{ aspectRatio: aspectRatio(active.observation) }}
        >
          <img
            src={active.url}
            alt={`${active.label} screenshot for ${step.step_id}`}
            loading="lazy"
          />
        </figure>
      ) : (
        <div className="screenshot-placeholder">
          <strong>Screenshot artifact not available.</strong>
          <span>{active?.observation?.image_path ?? "No image path recorded"}</span>
        </div>
      )}
      <p className="screenshot-caption">{screenshotCaption(active)}</p>

      {visibleCandidates.length > 0 && (
        <details className="raw-toggle">
          <summary>Screenshot details</summary>
          <dl className="screenshot-metadata">
            {visibleCandidates.map((candidate) => (
              <div key={candidate.slot}>
                <dt>{candidate.label}</dt>
                <dd>
                  <span>{valueOrMissing(candidate.observation?.observation_id)}</span>
                  <span>{valueOrMissing(candidate.observation?.image_path)}</span>
                  <span>Image: {dimensions(candidate.observation)}</span>
                  <span>Viewport: {viewportDimensions(candidate.observation)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </section>
  );
}

function RawBlock({ value }: { value: unknown }) {
  return (
    <details className="raw-toggle">
      <summary>View raw evidence</summary>
      <pre className="raw-block">{JSON.stringify(value ?? null, null, 2)}</pre>
    </details>
  );
}

function ErrorValue({ value }: { value: unknown }) {
  const text = valueOrMissing(value);
  const [expanded, setExpanded] = useState(false);

  if (text.length <= ERROR_PREVIEW_LIMIT) {
    return <span>{text}</span>;
  }

  return (
    <span className="evidence-error">
      <span className="evidence-error-text">
        {expanded ? text : `${text.slice(0, ERROR_PREVIEW_LIMIT).trimEnd()}\n...`}
      </span>
      <button
        type="button"
        className="evidence-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Show less" : "Show full error"}
      </button>
    </span>
  );
}

function DetailRows({
  rows,
  compactError = false,
}: {
  rows: Array<[string, unknown]>;
  compactError?: boolean;
}) {
  return (
    <dl className="property-grid">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>
            {key === "error" && compactError
              ? "Available in execution details"
              : key === "error"
                ? <ErrorValue value={value} />
                : valueOrMissing(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function stageSummary(stage: EvidenceStageId, step: Step): string {
  if (stage === "observation") {
    return step.observation ? "Screenshot" : "Unavailable";
  }
  if (stage === "model-context") {
    return hasObjectData(step.model_input) ? "Available" : "Unavailable";
  }
  if (stage === "action") {
    return step.action?.type ?? "Unavailable";
  }
  if (stage === "execution") {
    return step.execution?.status ?? "Unavailable";
  }
  if (stage === "post-state") {
    return step.post_state ? "available" : "Unavailable";
  }
  return "Unavailable";
}

function CollapsedStage({ stage, step }: { stage: EvidenceStageId; step: Step }) {
  const label = STAGES.find((item) => item.id === stage)?.label ?? stage;

  return (
    <details className="collapsed-stage">
      <summary>
        <span>{label}</span>
        <span>{stageSummary(stage, step)}</span>
      </summary>
      <StageDetail stage={stage} step={step} />
    </details>
  );
}

function StageDetail({ stage, step }: { stage: EvidenceStageId; step: Step }) {
  if (stage === "observation") {
    return (
      <>
        <DetailRows
          rows={[
            ["observation_id", step.observation?.observation_id],
            ["image_path", step.observation?.image_path],
            ["dimensions", dimensions(step.observation)],
            ["viewport", viewportDimensions(step.observation)],
          ]}
        />
        <RawBlock value={step.observation} />
      </>
    );
  }

  if (stage === "model-context") {
    return (
      <>
        <DetailRows
          rows={[
            ["model_call_id", step.model_input?.model_call_id],
            ["model", step.model_input?.model],
            ["observation_ids", step.model_input?.observation_ids?.join(", ")],
          ]}
        />
        <RawBlock value={step.model_input} />
      </>
    );
  }

  if (stage === "action") {
    const coordinates =
      step.action?.x !== null &&
      step.action?.x !== undefined &&
      step.action?.y !== null &&
      step.action?.y !== undefined
        ? `(${step.action.x}, ${step.action.y})`
        : "Not available";

    return (
      <>
        <DetailRows
          rows={[
            ["type", step.action?.type],
            ["coordinates", coordinates],
            ["target", step.action?.target],
            ["coordinate_space", step.action?.coordinate_space],
          ]}
        />
        <RawBlock value={step.action} />
      </>
    );
  }

  if (stage === "execution") {
    return (
      <>
        <DetailRows
          compactError
          rows={[
            ["status", step.execution?.status],
          ]}
        />
        <details className="raw-toggle execution-details">
          <summary>
            <Terminal size={14} aria-hidden="true" />
            View execution details
          </summary>
          <DetailRows rows={[["error", step.execution?.error]]} />
          <RawBlock value={step.execution} />
        </details>
      </>
    );
  }

  return (
    <>
      <DetailRows
        rows={[
          ["url", step.post_state?.url],
          ["window_title", step.post_state?.window_title],
          ["observation", step.post_state?.observation?.observation_id],
        ]}
      />
      <RawBlock value={step.post_state} />
    </>
  );
}

export function StepInspector({
  artifacts,
  resetKey,
  selectedFinding,
  step,
  stepIndex,
  totalSteps,
}: StepInspectorProps) {
  const [activeStage, setActiveStage] = useState<EvidenceStageId>("observation");

  useEffect(() => {
    if (step) {
      setActiveStage(defaultStage(step, selectedFinding));
    }
  }, [resetKey, selectedFinding, step]);

  if (!step) {
    return (
      <section className="panel step-inspector" aria-label="Step inspector">
        <h2>Inspector</h2>
        <p className="empty-copy">No step selected.</p>
      </section>
    );
  }

  return (
    <section className="panel step-inspector" aria-label="Step inspector">
      <ScreenshotViewer
        artifacts={artifacts}
        resetKey={resetKey}
        step={step}
        stepIndex={stepIndex}
        totalSteps={totalSteps}
      />

      <section className="evidence-chain" aria-label="Evidence chain">
        {STAGES.map((stage, index) => {
          const state = evidenceState(stage.id, step, artifacts);
          const StageIcon = stage.Icon;
          return (
            <div className="stage-wrap" key={stage.id}>
              <button
                type="button"
                className={`stage-button stage-${state} ${activeStage === stage.id ? "active" : ""}`}
                onClick={() => setActiveStage(stage.id)}
              >
                <span className="stage-icon">
                  <StageIcon size={16} aria-hidden="true" />
                </span>
                <span className="stage-label">{stage.label}</span>
                <span className="stage-summary">{stageSummary(stage.id, step)}</span>
                <span className="stage-mark" aria-label={state}>
                  <StageStatusIcon state={state} />
                </span>
              </button>
              {index < STAGES.length - 1 && <span className="stage-arrow" aria-hidden="true" />}
            </div>
          );
        })}
      </section>

      <section className="step-detail" aria-label="Step detail">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Step Detail</span>
            <h3>{STAGES.find((stage) => stage.id === activeStage)?.label}</h3>
          </div>
          <code>{step.step_id}</code>
        </div>
        <StageDetail stage={activeStage} step={step} />
        {activeStage !== "action" && <CollapsedStage stage="action" step={step} />}
        {activeStage !== "post-state" && <CollapsedStage stage="post-state" step={step} />}
      </section>
    </section>
  );
}
