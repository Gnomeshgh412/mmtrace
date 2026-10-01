export type Severity = "ERROR" | "WARNING" | "INFO";
export type ReportStatus = "PASS" | "FAIL";
export type ExecutionStatus = "success" | "failed" | "unknown" | string;
export interface AnalysisResponse {
  analysis_id: string;
  trace: Trace;
  report: Report;
  artifacts: Artifacts;
}

export interface Trace {
  trace_id: string;
  task?: string | null;
  agent?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  metadata?: Record<string, unknown> | null;
  steps: Step[];
}

export interface Step {
  step_id: string;
  observation?: Observation | null;
  model_input?: ModelInput | null;
  action?: Action | null;
  execution?: ExecutionResult | null;
  post_state?: PostState | null;
}

export interface Observation {
  observation_id?: string | null;
  image_path?: string | null;
  width?: number | null;
  height?: number | null;
  viewport_width?: number | null;
  viewport_height?: number | null;
  timestamp?: string | null;
}

export interface ModelInput {
  model_call_id?: string | null;
  model?: string | null;
  observation_ids?: string[] | null;
  timestamp?: string | null;
}

export interface Action {
  action_id?: string | null;
  type?: string | null;
  x?: number | null;
  y?: number | null;
  target?: string | null;
  coordinate_space?: string | null;
  timestamp?: string | null;
}

export interface ExecutionResult {
  status?: ExecutionStatus | null;
  error?: string | null;
  timestamp?: string | null;
}

export interface PostState {
  observation?: Observation | null;
  url?: string | null;
  window_title?: string | null;
  state_metadata?: Record<string, unknown> | null;
  timestamp?: string | null;
}

export interface Report {
  trace_id: string;
  status: ReportStatus;
  error_count: number;
  warning_count: number;
  info_count: number;
  findings: Finding[];
}

export interface Finding {
  rule_id: string;
  severity: Severity;
  step_id?: string | null;
  title: string;
  evidence?: Record<string, unknown> | null;
  explanation?: string | null;
  suggestion?: string | null;
}

export interface Artifacts {
  screenshots: Record<string, string>;
}

export type AdapterName = "generic" | "browser-use" | "osworld";

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
}

export interface AnalyzeTraceInput {
  adapter: AdapterName;
  file: File;
  artifactFile?: File | null;
}

export interface AnalyzeError {
  code: string;
  message: string;
}
