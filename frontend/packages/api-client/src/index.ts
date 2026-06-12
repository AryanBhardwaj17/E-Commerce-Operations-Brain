export type QueryRequest = {
  query: string;
  user_id?: string;
  date_str?: string;
};

export type QueryResponse = {
  run_id: string;
  status: string;
  message: string;
};

export type DomainFinding = {
  domain: string;
  summary: string;
  confidence: number;
  anomalies?: string[];
  contributing_factors?: string[];
};

export type InventoryItem = {
  product_id: string;
  product_name: string;
  quantity_available: number;
  reorder_point: number;
  status: string;
  days_until_stockout?: number | null;
  unit_price?: number | null;
  currency?: string | null;
  effective_price?: number | null;
  active_discount?: {
    discount_plan_id: string;
    product_id: string;
    plan_name: string;
    discount_pct: number;
    starts_on?: string | null;
    ends_on?: string | null;
  } | null;
};

export type RiskLevel = "low" | "medium" | "high";

export type ActionProposal = {
  action_name: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  rationale: string;
  estimated_impact: string;
  risk_level: RiskLevel;
};

export type ActionStatus = "executed" | "failed";

export type ActionRecord = {
  action_name: string;
  tool_name: string;
  status: ActionStatus;
  result?: Record<string, unknown> | null;
  error?: string | null;
  idempotency_key?: string | null;
  execution_id?: string | null;
  executed_at?: string | null;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
};

export type ReportKind =
  | "analysis"
  | "inventory_list"
  | "action_confirmation"
  | "history_response"
  | "out_of_scope";

export type FinalReport = {
  run_id: string;
  query: string;
  report_kind?: ReportKind;
  executive_summary: string;
  confidence_score: number;
  recommendations: string[];
  data_gaps: string[];
  inventory_items?: InventoryItem[];
  actions_taken?: ActionRecord[];
  actions_pending_approval?: ActionProposal[];
  analysis?: {
    primary_root_cause: string;
    contributing_factors: string[];
    findings: DomainFinding[];
  } | null;
};

export type RunStatus = {
  run_id?: string;
  status: string;
  approval_status?: string;
  updated_at?: string;
  error?: string;
  interrupts?: unknown[];
  final_report?: FinalReport | null;
};

export type RunEvent = {
  type: string;
  timestamp: string;
  status?: string;
  node?: string;
  detail?: string;
  payload?: Record<string, unknown>;
};

export type QueryEventsResponse = {
  run_id: string;
  events: RunEvent[];
};

export type PendingApproval = {
  run_id: string;
  context_summary: string;
  proposals: ActionProposal[];
  requested_at: string;
};

export type ApproveActionsRequest = {
  approved_action_names: string[];
};

export type RejectActionsRequest = {
  reason?: string;
};

export type ApprovalDecisionResponse = {
  run_id: string;
  status: string;
  approved?: string[];
  rejected?: string[];
  reason?: string;
};

export type BackendConnection = {
  baseUrl: string;
  apiKey?: string;
};

export class OpsBrainApiError extends Error {
  status: number;
  detail: string;

  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = "OpsBrainApiError";
    this.status = status;
    this.detail = detail;
  }
}

const DEFAULT_BACKEND_BASE_URL = "http://localhost:8000";

function normaliseBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (payload && payload.detail) {
      return String(payload.detail);
    }
  } catch {
    // Fall back to text/status below.
  }

  const bodyText = await response.text().catch(() => "");
  return bodyText || response.statusText || `Request failed with status ${response.status}`;
}

async function requestJson<T>(
  connection: BackendConnection,
  path: string,
  init: RequestInit,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (connection.apiKey) {
    headers.set("x-api-key", connection.apiKey);
  }
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${normaliseBaseUrl(connection.baseUrl)}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new OpsBrainApiError(detail, response.status, detail);
  }

  return (await response.json()) as T;
}

export function getServerBackendConnection(
  env: Record<string, string | undefined> = process.env,
): BackendConnection {
  return {
    baseUrl: env.EOB_API_BASE_URL?.trim() || DEFAULT_BACKEND_BASE_URL,
    apiKey: env.EOB_API_KEY?.trim() || undefined,
  };
}

export async function submitQuery(
  connection: BackendConnection,
  request: QueryRequest,
): Promise<QueryResponse> {
  return requestJson<QueryResponse>(connection, "/query", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getQueryStatus(
  connection: BackendConnection,
  runId: string,
): Promise<RunStatus> {
  return requestJson<RunStatus>(connection, `/query/${runId}/status`, {
    method: "GET",
  });
}

export async function getQueryEvents(
  connection: BackendConnection,
  runId: string,
): Promise<QueryEventsResponse> {
  return requestJson<QueryEventsResponse>(connection, `/query/${runId}/events`, {
    method: "GET",
  });
}

export async function getPendingActions(
  connection: BackendConnection,
  runId: string,
): Promise<PendingApproval> {
  return requestJson<PendingApproval>(connection, `/actions/${runId}/pending`, {
    method: "GET",
  });
}

export async function approveActions(
  connection: BackendConnection,
  runId: string,
  request: ApproveActionsRequest,
): Promise<ApprovalDecisionResponse> {
  return requestJson<ApprovalDecisionResponse>(connection, `/actions/${runId}/approve`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function rejectActions(
  connection: BackendConnection,
  runId: string,
  request: RejectActionsRequest,
): Promise<ApprovalDecisionResponse> {
  return requestJson<ApprovalDecisionResponse>(connection, `/actions/${runId}/reject`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function toErrorResponse(error: unknown): {
  status: number;
  body: { detail: string };
} {
  if (error instanceof OpsBrainApiError) {
    return {
      status: error.status,
      body: { detail: error.detail },
    };
  }

  return {
    status: 500,
    body: { detail: error instanceof Error ? error.message : "Unexpected server error." },
  };
}