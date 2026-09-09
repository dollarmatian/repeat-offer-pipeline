export type Outcome = "decided" | "declined" | "referred";

export interface StageOutcome {
  attempt: number;
  position: number;
  stage: string;
  rule: string;
  outcome: "pass" | "fail" | "refer";
  reason: string;
  values: Record<string, unknown>;
  overridden: boolean;
}

export interface DecisionRecord {
  reference: string;
  id: number;
  ruleset: string;
  version: string;
  subject_reference: string;
  inputs: Record<string, unknown>;
  flag_state: Record<string, unknown>;
  outcome: Outcome;
  stopped_at_stage: string | null;
  decision: Record<string, unknown>;
  stages: StageOutcome[];
  created_at: string;
}

export interface HistoryEntry {
  at: string;
  by: string;
  action: "override" | "decline";
  note: string;
  stage: string;
  rule_name: string;
  values: Record<string, unknown>;
}

export interface ExceptionSummary {
  id: number;
  status: "open" | "resolved";
  stage: string;
  rule: string;
  reason: string;
  decision_reference: string;
  subject_reference: string;
  ruleset: string;
  version: string;
  history: HistoryEntry[];
  opened_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface ExceptionDetail extends ExceptionSummary {
  record: DecisionRecord;
}

export interface Resolution {
  action: "override" | "decline";
  resolved_by: string;
  note: string;
  values?: Record<string, string>;
}

export interface Api {
  listExceptions(status: "open" | "resolved" | "all"): Promise<ExceptionSummary[]>;
  getException(id: number): Promise<ExceptionDetail>;
  resolveException(id: number, resolution: Resolution): Promise<ExceptionDetail>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, body.error ?? response.statusText);
  }
  return body as T;
}

export function createApi(base = "/api"): Api {
  return {
    async listExceptions(status) {
      const body = await request<{ exceptions: ExceptionSummary[] }>(
        `${base}/exceptions/?status=${status}`,
      );
      return body.exceptions;
    },
    getException(id) {
      return request<ExceptionDetail>(`${base}/exceptions/${id}/`);
    },
    resolveException(id, resolution) {
      return request<ExceptionDetail>(`${base}/exceptions/${id}/resolve/`, {
        method: "POST",
        body: JSON.stringify(resolution),
      });
    },
  };
}
