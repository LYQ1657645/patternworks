export type Job = {
  id: string;
  kind: "DIAGNOSTIC" | "LIST_WORKSHEETS" | "CONNECT_S3" | "IMPORT_DATASET" | "REPLACE_TEXT" | "GENERATE_RULE" | "APPLY_RULE" | "PREVIEW_TRANSFORM" | "APPLY_TRANSFORM" | "EXPORT_CSV";
  connection_id: string | null;
  dataset_id: string | null;
  rule_id: string | null;
  transformation_id: string | null;
  status: "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED";
  progress: number;
  stage: string;
  error_message: string;
  error_code?: string;
  result: Record<string, unknown>;
  attempt_count: number;
  recovery_count: number;
  heartbeat_at: string | null;
  retry_allowed: boolean;
  retry_unavailable_reason?: string;
  dataset_available?: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type S3File = {
  key: string;
  size: number;
  last_modified: string;
  format: string;
};
export type FilePage = {
  files: S3File[];
  next_cursor: string | null;
  bucket: string;
};
export type Health = {
  status: string;
  checks: Record<string, string>;
  openai_configured: boolean;
};
export type Dataset = {
  id: string;
  created_at: string;
  lifecycle: "ACTIVE" | "TRASH" | "PURGING" | "PURGED";
  retention_days: number;
  expires_at: string | null;
  trashed_at: string | null;
  purge_after: string | null;
  purged_at: string | null;
  trash_reason: string;
  parent_id: string | null;
  source_key: string;
  source_format: string;
  sheet_name: string;
  status: "PENDING" | "READY" | "FAILED" | "CANCELLED";
  row_count: number;
  columns: { key: string; name: string; type: string }[];
  metadata: { spark_version?: string; partition_count?: number; sheet_names?: string[]; operation?: string;
    matched_rows?: number; match_count?: number; changed_rows?: number; regex_engine?: string;
    columns?: string[]; matched_cells?: number; changed_cells?: number;
    column_stats?: Record<string, { matched_rows: number; match_count: number; changed_rows: number }>;
    status_counts?: Record<string, number>; llm_usage?: { model_calls: number; cached_values: number; unique_values: number } };
};
export type DatasetPage = {
  dataset_id: string;
  columns: Dataset["columns"];
  total_rows: number;
  rows: { row_number: number; cells: (string | null)[] }[];
  next_cursor: number | null;
  preview_cell_limit: number;
};
export type RuleExample = { row_number: number; before: string | null; after: string | null; matched: boolean;
  match_count: number; before_truncated?: boolean; after_truncated?: boolean };
export type ColumnPreview = { column: string; name: string; sampled_rows: number; matched_rows: number;
  match_count: number; changed_rows: number; examples: RuleExample[] };

export type RegexRule = {
  id: string;
  dataset_id: string;
  column: string;
  columns?: string[];
  instruction: string;
  status: "PENDING" | "READY" | "FAILED" | "CANCELLED";
  pattern: string;
  replacement: string;
  ignore_case: boolean;
  explanation: string;
  model: string;
  policy_version: string;
  cache_hit: boolean;
  preview: { sampled_rows: number; matched_rows: number; cell_character_limit: number;
    full_values?: boolean;
    column_previews?: ColumnPreview[]; matched_cells?: number; changed_rows?: number; match_count?: number;
    validation_examples?: { matching: string[]; non_matching: string[] };
    examples: RuleExample[] };
  usage: { input_tokens: number; output_tokens: number };
};

export type LLMTransformation = {
  id: string; dataset_id: string; kind: "DATE" | "CATEGORY"; column: string; instruction: string;
  options: { date_order?: string; labels?: string[]; fallback?: string };
  status: "PENDING" | "READY" | "FAILED" | "CANCELLED"; model: string;
  request_budget?: number; requests_used?: number; requests_completed?: number;
  input_tokens?: number; output_tokens?: number;
  plan?: { distinct_values: number; pending_values: number; estimated_new_requests: number; remaining_requests: number };
  preview: { sampled_rows: number; counts: Record<string, number>;
    examples: { row_number: number; before: string | null; after: string | null; status: string }[] };
  usage: { model_calls: number; cached_values: number; unique_values: number; input_tokens: number; output_tokens: number };
};

let csrfToken = "";
let sessionPromise: Promise<void> | null = null;

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string, public job?: Job) {
    super(message);
    this.name = "ApiError";
  }
}

export function submissionError(error: unknown, onJob: (job: Job) => void): string {
  if (error instanceof ApiError && error.job) onJob(error.job);
  return error instanceof Error ? error.message : "The request could not be completed.";
}

async function session(): Promise<void> {
  if (!sessionPromise) {
    sessionPromise = fetch("/api/session/", { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok)
          throw new Error("Could not start a session. Check the API service.");
        csrfToken = (await r.json()).csrf_token;
      })
      .catch((error) => {
        sessionPromise = null;
        throw error;
      });
  }
  return sessionPromise;
}

export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  await session();
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(body === undefined ? {} : { "X-CSRFToken": csrfToken }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response.");
  }
  if (!response.ok) {
    const validation = Object.entries(data).find(([, value]) =>
      Array.isArray(value),
    );
    const failedJob = data && typeof data.id === "string" && data.status === "FAILED"
      && typeof data.kind === "string" && typeof data.retry_allowed === "boolean" ? data as Job : undefined;
    throw new ApiError(
      data.detail ||
        data.error_message ||
        (validation
          ? `${validation[0]}: ${validation[1]}`
          : "The request could not be completed."), response.status, data.code || data.error_code, failedJob,
    );
  }
  return data as T;
}

export async function health(): Promise<Health> {
  const response = await fetch("/api/health/");
  return response.json();
}
