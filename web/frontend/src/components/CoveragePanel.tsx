import type {
  EvaluationCoverage,
  EvaluationOutcome,
  MissingEvidence,
  RuleEvaluation,
} from "../types";

interface CoveragePanelProps {
  evaluations: RuleEvaluation[] | null;
}

const RULE_TITLES: Record<string, string> = {
  MMTRACE001: "Missing Observation",
  MMTRACE002: "Observation Not In Model Context",
  MMTRACE003: "Coordinate Out Of Frame",
  MMTRACE004: "Coordinate Space Mismatch",
  MMTRACE005: "Stale Observation",
  MMTRACE006: "Missing Post-Action Verification",
  MMTRACE007: "Explicit Execution Failure",
};

const MISSING_EVIDENCE_LABELS: Record<string, string> = {
  observation: "Observation",
  "observation.id": "Observation ID",
  model_input: "Model input",
  "model_input.observation_ids": "Observation IDs in model context",
  "action.coordinates": "Action coordinates",
  "observation.frame_dimensions": "Frame dimensions",
  "action.coordinate_space": "Action coordinate space",
  "executor.coordinate_space": "Expected coordinate space",
  "observation.timestamp": "Observation timestamp",
  "action.timestamp": "Action timestamp",
  execution: "Execution result",
  "execution.status": "Execution status",
};

const COVERAGE_LABELS: Record<EvaluationCoverage, string> = {
  FULL: "Full coverage",
  PARTIAL: "Partial coverage",
  NOT_EVALUABLE: "Not evaluable",
  NOT_APPLICABLE: "Not applicable",
};

const OUTCOME_LABELS: Record<EvaluationOutcome, string> = {
  PASS: "PASS",
  WARNING: "WARNING",
  ERROR: "ERROR",
  NONE: "NONE",
};

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
}

function missingEvidenceLabel(item: MissingEvidence) {
  return MISSING_EVIDENCE_LABELS[item.code] ?? item.code;
}

function summaryCounts(evaluations: RuleEvaluation[]) {
  return evaluations.reduce(
    (counts, evaluation) => {
      counts[evaluation.coverage] += 1;
      return counts;
    },
    {
      FULL: 0,
      PARTIAL: 0,
      NOT_EVALUABLE: 0,
      NOT_APPLICABLE: 0,
    } satisfies Record<EvaluationCoverage, number>,
  );
}

function shouldShowOutcome(evaluation: RuleEvaluation) {
  return evaluation.outcome !== "NONE";
}

function evaluatedCopy(evaluation: RuleEvaluation) {
  if (evaluation.coverage === "NOT_APPLICABLE") {
    return "No applicable units in this trace.";
  }
  return `${evaluation.evaluable_units} / ${evaluation.applicable_units} evaluated`;
}

function RuleCoverageRow({ evaluation }: { evaluation: RuleEvaluation }) {
  const showMissing =
    evaluation.not_evaluable_units > 0 && evaluation.missing_evidence.length > 0;

  return (
    <section className="coverage-rule-row" aria-label={`${evaluation.rule_id} coverage`}>
      <div className="coverage-rule-main">
        <div className="coverage-rule-title">
          <code>{evaluation.rule_id}</code>
          <h2>{RULE_TITLES[evaluation.rule_id] ?? evaluation.rule_id}</h2>
        </div>
        <div className="coverage-rule-meta">
          <span>{evaluatedCopy(evaluation)}</span>
          {evaluation.finding_count > 0 && (
            <span className={`coverage-finding-count outcome-${evaluation.outcome.toLowerCase()}`}>
              {evaluation.finding_count} {pluralize(evaluation.finding_count, "finding")}
            </span>
          )}
        </div>
      </div>
      <div className="coverage-rule-status">
        {shouldShowOutcome(evaluation) && (
          <span className={`coverage-badge outcome-${evaluation.outcome.toLowerCase()}`}>
            {OUTCOME_LABELS[evaluation.outcome]}
          </span>
        )}
        <span className={`coverage-badge coverage-${evaluation.coverage.toLowerCase()}`}>
          {COVERAGE_LABELS[evaluation.coverage]}
        </span>
      </div>
      {showMissing && (
        <div className="coverage-missing" aria-label={`${evaluation.rule_id} missing evidence`}>
          <h3>Missing evidence</h3>
          <dl>
            {evaluation.missing_evidence.map((item) => (
              <div key={item.code}>
                <dt>{missingEvidenceLabel(item)}</dt>
                <dd>×{item.count}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}

export function CoveragePanel({ evaluations }: CoveragePanelProps) {
  if (evaluations === null) {
    return (
      <main className="coverage-view">
        <section className="coverage-shell">
          <div className="coverage-heading">
            <span className="eyebrow">Coverage</span>
            <h1>Coverage unavailable</h1>
            <p>
              Coverage data was not stored for this analysis. This snapshot predates
              persisted rule evaluations.
            </p>
          </div>
          <section className="coverage-legacy-state" role="status">
            <h2>Import this trace again to generate evidence coverage.</h2>
            <p>
              Legacy analyses still preserve trace, report, and artifact data, but they
              cannot show frozen rule evaluability.
            </p>
          </section>
        </section>
      </main>
    );
  }

  if (evaluations.length === 0) {
    return (
      <main className="coverage-view">
        <section className="coverage-shell">
          <div className="coverage-heading">
            <span className="eyebrow">Coverage</span>
            <h1>No rule evaluations were stored.</h1>
            <p>The analysis response contains an empty evaluations list.</p>
          </div>
        </section>
      </main>
    );
  }

  const counts = summaryCounts(evaluations);

  return (
    <main className="coverage-view">
      <section className="coverage-shell" aria-label="Rule evidence coverage">
        <div className="coverage-heading">
          <span className="eyebrow">Coverage</span>
          <h1>Evidence coverage</h1>
          <p>
            Shows which MMTrace checks were fully evaluated, partially evaluated,
            or could not be evaluated from the recorded evidence.
          </p>
        </div>
        <dl className="coverage-summary" aria-label="Coverage summary">
          <div>
            <dt>Full</dt>
            <dd>{counts.FULL}</dd>
          </div>
          <div>
            <dt>Partial</dt>
            <dd>{counts.PARTIAL}</dd>
          </div>
          <div>
            <dt>Not evaluable</dt>
            <dd>{counts.NOT_EVALUABLE}</dd>
          </div>
          <div>
            <dt>N/A</dt>
            <dd>{counts.NOT_APPLICABLE}</dd>
          </div>
        </dl>
        <div className="coverage-rule-list">
          {evaluations.map((evaluation) => (
            <RuleCoverageRow key={evaluation.rule_id} evaluation={evaluation} />
          ))}
        </div>
      </section>
    </main>
  );
}
