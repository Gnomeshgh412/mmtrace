import type { AdapterName, AnalyzeError } from "../types";

interface TraceLoaderProps {
  adapter: AdapterName;
  error: AnalyzeError | null;
  artifactFile: File | null;
  isLoading: boolean;
  selectedFile: File | null;
  onAdapterChange: (adapter: AdapterName) => void;
  onArtifactFileChange: (file: File | null) => void;
  onFileChange: (file: File | null) => void;
  onAnalyze: () => void;
}

export function TraceLoader({
  adapter,
  artifactFile,
  error,
  isLoading,
  selectedFile,
  onAdapterChange,
  onArtifactFileChange,
  onFileChange,
  onAnalyze,
}: TraceLoaderProps) {
  return (
    <section className="trace-loader" aria-label="Trace loader">
      <div className="loader-field">
        <label htmlFor="adapter">Adapter</label>
        <select
          id="adapter"
          value={adapter}
          disabled={isLoading}
          onChange={(event) => onAdapterChange(event.target.value as AdapterName)}
        >
          <option value="generic">generic</option>
          <option value="browser-use">browser-use</option>
        </select>
      </div>

      <div className="loader-field file-field">
        <label htmlFor="trace-file">Trace file</label>
        <input
          id="trace-file"
          type="file"
          accept=".json,application/json"
          disabled={isLoading}
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
      </div>

      <div className="loader-field file-field">
        <label htmlFor="artifact-file">Screenshot bundle optional</label>
        <input
          id="artifact-file"
          type="file"
          accept=".zip,application/zip"
          disabled={isLoading}
          onChange={(event) => onArtifactFileChange(event.target.files?.[0] ?? null)}
        />
        {artifactFile && <span className="file-note">{artifactFile.name}</span>}
      </div>

      <button
        type="button"
        className="analyze-button"
        disabled={isLoading || !selectedFile}
        onClick={onAnalyze}
      >
        {isLoading ? "Analyzing..." : "Analyze"}
      </button>

      {error && (
        <div className="loader-error" role="alert">
          <strong>Unable to analyze trace</strong>
          <span>{error.code}</span>
          <p>{error.message}</p>
        </div>
      )}
    </section>
  );
}
