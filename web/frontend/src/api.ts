import type {
  AnalysisResponse,
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
