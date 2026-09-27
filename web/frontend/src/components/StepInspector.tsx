import { useEffect, useMemo, useState } from "react";
import type { Artifacts, Observation, Step } from "../types";

interface StepInspectorProps {
  artifacts: Artifacts;
  resetKey: string;
  step: Step | null;
}

function valueOrMissing(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type ScreenshotSlot = "before" | "after";

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

function viewportDimensions(observation?: Observation | null): string {
  if (!observation?.viewport_width || !observation.viewport_height) {
    return "Not available";
  }
  return `${observation.viewport_width} × ${observation.viewport_height}`;
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

function ScreenshotViewer({
  artifacts,
  resetKey,
  step,
}: {
  artifacts: Artifacts;
  resetKey: string;
  step: Step;
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
    <section className="inspector-section screenshot-section" aria-label="Screenshot">
      <div className="screenshot-heading">
        <h3>Screenshot</h3>
        {hasMultipleScreenshots && (
          <div className="screenshot-tabs" aria-label="Screenshot view">
            {candidates
              .filter((candidate) => candidate.url)
              .map((candidate) => (
                <button
                  key={candidate.slot}
                  type="button"
                  className={activeSlot === candidate.slot ? "active" : ""}
                  onClick={() => setActiveSlot(candidate.slot)}
                >
                  {candidate.label}
                </button>
              ))}
          </div>
        )}
      </div>

      {active?.url ? (
        <figure className="screenshot-viewer">
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

      {visibleCandidates.length > 0 && (
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
      )}
    </section>
  );
}

export function StepInspector({ artifacts, resetKey, step }: StepInspectorProps) {
  if (!step) {
    return (
      <section className="panel step-inspector" aria-label="Step inspector">
        <h2>Step Inspector</h2>
        <p className="empty-copy">No step selected.</p>
      </section>
    );
  }

  const coordinates =
    step.action?.x !== null &&
    step.action?.x !== undefined &&
    step.action?.y !== null &&
    step.action?.y !== undefined
      ? `(${step.action.x}, ${step.action.y})`
      : "Not available";

  return (
    <section className="panel step-inspector" aria-label="Step inspector">
      <div className="panel-heading">
        <h2>{step.step_id}</h2>
        <span className="muted">{step.action?.type ?? "No action"}</span>
      </div>

      <ScreenshotViewer artifacts={artifacts} resetKey={resetKey} step={step} />

      <section className="inspector-section" aria-label="Observation">
        <h3>Observation</h3>
        <dl className="property-grid">
          <dt>observation_id</dt>
          <dd>{valueOrMissing(step.observation?.observation_id)}</dd>
          <dt>image_path</dt>
          <dd>{valueOrMissing(step.observation?.image_path)}</dd>
          <dt>dimensions</dt>
          <dd>{dimensions(step.observation)}</dd>
          <dt>viewport dimensions</dt>
          <dd>{viewportDimensions(step.observation)}</dd>
        </dl>
      </section>

      <section className="inspector-section" aria-label="Action">
        <h3>Action</h3>
        <dl className="property-grid">
          <dt>type</dt>
          <dd>{valueOrMissing(step.action?.type)}</dd>
          <dt>coordinates</dt>
          <dd>{coordinates}</dd>
          <dt>target</dt>
          <dd>{valueOrMissing(step.action?.target)}</dd>
          <dt>coordinate_space</dt>
          <dd>{valueOrMissing(step.action?.coordinate_space)}</dd>
        </dl>
      </section>

      <section className="inspector-section" aria-label="Execution">
        <h3>Execution</h3>
        <dl className="property-grid">
          <dt>status</dt>
          <dd>{valueOrMissing(step.execution?.status)}</dd>
          <dt>error</dt>
          <dd>{valueOrMissing(step.execution?.error)}</dd>
        </dl>
      </section>

      <section className="inspector-section" aria-label="Post-State">
        <h3>Post-State</h3>
        <dl className="property-grid">
          <dt>url</dt>
          <dd>{valueOrMissing(step.post_state?.url)}</dd>
          <dt>window_title</dt>
          <dd>{valueOrMissing(step.post_state?.window_title)}</dd>
          <dt>observation reference</dt>
          <dd>{valueOrMissing(step.post_state?.observation?.observation_id)}</dd>
        </dl>
      </section>
    </section>
  );
}
