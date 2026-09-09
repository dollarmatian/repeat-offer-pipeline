import type { Api, ExceptionDetail, ExceptionSummary, Resolution } from "../api";

export const summary: ExceptionSummary = {
  id: 7,
  status: "open",
  stage: "eligibility",
  rule: "lending.missed_payments",
  reason: "1 missed payment in the last 12 months needs a look",
  decision_reference: "dec_0123456789abcdef",
  subject_reference: "CUST-3",
  ruleset: "lending",
  version: "1",
  history: [],
  opened_at: "2026-09-09T10:00:00Z",
  resolved_at: null,
  resolved_by: null,
};

export const detail: ExceptionDetail = {
  ...summary,
  record: {
    reference: summary.decision_reference,
    id: 42,
    ruleset: "lending",
    version: "1",
    subject_reference: "CUST-3",
    inputs: { loans_repaid: 3, missed_payments_last_12m: 1, sector: "retail" },
    flag_state: { flag: null, matched: false, bucket: 17, version: "1" },
    outcome: "referred",
    stopped_at_stage: "eligibility",
    decision: {},
    stages: [
      {
        attempt: 1,
        position: 1,
        stage: "eligibility",
        rule: "lending.repayment_history",
        outcome: "pass",
        reason: "3 loan(s) repaid",
        values: {},
        overridden: false,
      },
      {
        attempt: 1,
        position: 2,
        stage: "eligibility",
        rule: "lending.missed_payments",
        outcome: "refer",
        reason: "1 missed payment in the last 12 months needs a look",
        values: {},
        overridden: false,
      },
    ],
    created_at: "2026-09-09T10:00:00Z",
  },
};

export function resolved(resolution: Resolution): ExceptionDetail {
  return {
    ...detail,
    status: "resolved",
    resolved_by: resolution.resolved_by,
    resolved_at: "2026-09-09T11:00:00Z",
    history: [
      {
        at: "2026-09-09T11:00:00Z",
        by: resolution.resolved_by,
        action: resolution.action,
        note: resolution.note,
        stage: "eligibility",
        rule_name: "lending.missed_payments",
        values: resolution.values ?? {},
      },
    ],
    record: {
      ...detail.record,
      outcome: resolution.action === "override" ? "decided" : "declined",
      stopped_at_stage: null,
      decision: resolution.action === "override" ? { rate: "0.019", amount: "20000" } : {},
      stages: [
        ...detail.record.stages,
        {
          attempt: 2,
          position: 2,
          stage: "eligibility",
          rule: "lending.missed_payments",
          outcome: "pass",
          reason: `overridden by ${resolution.resolved_by}`,
          values: {},
          overridden: true,
        },
      ],
    },
  };
}

export function fakeApi(overrides: Partial<Api> = {}): Api & { calls: Resolution[] } {
  const calls: Resolution[] = [];
  return {
    calls,
    listExceptions: async (status) => (status === "open" ? [summary] : []),
    getException: async () => detail,
    resolveException: async (_id, resolution) => {
      calls.push(resolution);
      return resolved(resolution);
    },
    ...overrides,
  };
}
