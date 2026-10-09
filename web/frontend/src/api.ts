import type {
  AnalysisListFilters,
  AnalysisResponse,
  AnalysisSummary,
  AnalyzeError,
  AnalyzeTraceInput,
  ApiErrorPayload,
} from "./types";

export class TraceAnalyzeError extends Error {
  code: string;

  constructor(error: AnalyzeError) {
    super(error.message);
    this.name = "TraceAnalyzeError";
    this.code = error.code;
  }
}

export async function analyzeTrace({
  adapter,
  artifactFile,
  file,
}: AnalyzeTraceInput): Promise<AnalysisResponse> {
  const body = new FormData();
  body.append("adapter", adapter);
  body.append("trace_file", file);
  if (artifactFile) {
    body.append("artifacts", artifactFile);
  }

  const response = await fetch("/api/analyze", {
    method: "POST",
    body,
  });

  if (!response.ok) {
    throw new TraceAnalyzeError(await parseApiError(response));
  }

  return response.json() as Promise<AnalysisResponse>;
}

export async function listAnalyses(
  filters: AnalysisListFilters = {},
  signal?: AbortSignal,
): Promise<AnalysisSummary[]> {
  const params = new URLSearchParams();
  const search = filters.search?.trim();
  if (search) params.set("search", search);
  if (filters.status) params.set("status", filters.status);
  if (filters.adapter) params.set("adapter", filters.adapter);
  if (filters.findings) params.set("findings", filters.findings);

  const query = params.toString();
  const response = await fetch(`/api/analyses${query ? `?${query}` : ""}`, { signal });

  if (!response.ok) {
    throw new TraceAnalyzeError(await parseApiError(response));
  }

  return response.json() as Promise<AnalysisSummary[]>;
}

export async function getAnalysis(
  analysisId: string,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  const response = await fetch(`/api/analyses/${encodeURIComponent(analysisId)}`, {
    signal,
  });

  if (!response.ok) {
    throw new TraceAnalyzeError(await parseApiError(response));
  }

  return response.json() as Promise<AnalysisResponse>;
}

async function parseApiError(response: Response): Promise<AnalyzeError> {
  let payload: ApiErrorPayload | null = null;

  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    payload = null;
  }

  return {
    code: payload?.error?.code ?? "INTERNAL_ERROR",
    message:
      payload?.error?.message ??
      `Request failed with HTTP status ${response.status}.`,
  };
}
