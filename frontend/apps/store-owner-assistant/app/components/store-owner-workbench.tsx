"use client";

import { startTransition, useEffect, useState, type FormEvent } from "react";

import type {
  ActionRecord,
  ApprovalDecisionResponse,
  FinalReport,
  InventoryItem,
  PendingApproval,
  QueryResponse,
  ReportKind,
  RunStatus,
} from "@eob/api-client";

const SAMPLE_PROMPTS = [
  "Investigate the sudden drop in conversion rate after the weekend campaign launch.",
  "Explain why repeat purchase rate fell after the pricing update and suggest next actions.",
  "Audit the current stockout risk before the weekend promotion and flag high-impact products.",
];
const DEFAULT_USER_ID = "store_owner";
const POLLING_STATUSES = new Set(["running", "pending_approval"]);

function todayDateString(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatTimestamp(value?: string): string {
  if (!value) {
    return "just now";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function humanize(value: string): string {
  return value
    .replaceAll(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected request failure.";
}

function formatCurrencyValue(amount?: number | null, currency?: string | null): string {
  if (typeof amount !== "number") {
    return "-";
  }

  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatStockoutDays(value?: number | null): string {
  if (typeof value !== "number") {
    return "-";
  }
  return `${value}`;
}

function describeDiscount(item: InventoryItem): string {
  if (!item.active_discount) {
    return "-";
  }

  const endsOn = item.active_discount.ends_on ? ` until ${item.active_discount.ends_on}` : "";
  return `${item.active_discount.discount_pct}% off${endsOn}`;
}

function getResultRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function getResultProduct(record: ActionRecord): InventoryItem | null {
  const result = getResultRecord(record.result);
  if (!result) {
    return null;
  }

  const product = getResultRecord(result.product) ?? getResultRecord(result.after);
  return product ? (product as unknown as InventoryItem) : null;
}

async function readJson<T>(input: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(input, {
    ...init,
    headers,
    cache: "no-store",
  });

  const payload = (await response.json().catch(() => null)) as
    | { detail?: unknown }
    | null;

  if (!response.ok) {
    throw new Error(
      payload && payload.detail
        ? String(payload.detail)
        : `Request failed with status ${response.status}`,
    );
  }

  return payload as T;
}

function describeAction(record: ActionRecord): string | null {
  const label = record.action_name.trim() || record.tool_name.trim();
  if (!label) {
    return null;
  }

  const humanizedLabel = humanize(label);
  if (record.status === "failed") {
    return record.error ? `${humanizedLabel} failed: ${record.error}` : `${humanizedLabel} failed.`;
  }

  const result = getResultRecord(record.result);
  const product = getResultProduct(record);

  if (record.tool_name === "decrease_inventory_quantity" && result && product) {
    const quantityDelta = Number(result.applied_quantity_delta ?? result.requested_quantity_delta ?? 0);
    return `Removed ${quantityDelta} units from ${product.product_id}. ${product.quantity_available} remain available.`;
  }

  if (record.tool_name === "increase_inventory_quantity" && result && product) {
    const quantityDelta = Number(result.quantity_delta ?? 0);
    return `Added ${quantityDelta} units to ${product.product_id}. ${product.quantity_available} are now available.`;
  }

  if (record.tool_name === "remove_inventory_item" && product) {
    return `${product.product_id} was removed from the active inventory catalog.`;
  }

  if (record.tool_name === "update_inventory_price" && product) {
    return `Updated ${product.product_id} price to ${formatCurrencyValue(product.unit_price, product.currency)}.`;
  }

  if (record.tool_name === "create_discount_plan" && result) {
    const discountPlan = getResultRecord(result.discount_plan);
    const productId = product?.product_id ?? "the requested SKU";
    const discountPct = discountPlan?.discount_pct;
    if (typeof discountPct === "number") {
      return `Created a ${discountPct}% discount for ${productId}.`;
    }
  }

  if (record.tool_name === "update_discount_plan" && result) {
    const discountPlan = getResultRecord(result.discount_plan);
    const discountPct = discountPlan?.discount_pct;
    const discountPlanId = discountPlan?.discount_plan_id;
    if (typeof discountPct === "number" && typeof discountPlanId === "string") {
      return `Updated ${discountPlanId} to ${discountPct}% off.`;
    }
  }

  if (record.tool_name === "deactivate_discount_plan" && result) {
    const discountPlan = getResultRecord(result.discount_plan);
    const discountPlanId = discountPlan?.discount_plan_id;
    if (typeof discountPlanId === "string") {
      return `Deactivated ${discountPlanId}.`;
    }
  }

  return `${humanizedLabel} completed`;
}

function inferReportKind(report: FinalReport): ReportKind {
  if (report.report_kind) {
    return report.report_kind;
  }

  if (report.analysis) {
    const query = report.query.toLowerCase();
    if (Boolean(report.inventory_items?.length) && /(inventory|stock|sku|item|product)/.test(query)) {
      return "inventory_list";
    }
    return "analysis";
  }

  if (report.actions_taken?.length) {
    return "action_confirmation";
  }

  if (report.inventory_items?.length) {
    return "inventory_list";
  }

  return "analysis";
}

function sortInventoryItems(items: InventoryItem[]): InventoryItem[] {
  const statusWeight: Record<string, number> = {
    stockout: 0,
    low: 1,
    healthy: 2,
  };

  return [...items].sort((left, right) => {
    const leftWeight = statusWeight[left.status] ?? 99;
    const rightWeight = statusWeight[right.status] ?? 99;

    if (leftWeight !== rightWeight) {
      return leftWeight - rightWeight;
    }

    return left.product_name.localeCompare(right.product_name);
  });
}

function ApprovalPanel({
  approval,
  selectedActions,
  isSubmitting,
  onToggleAction,
  onApprove,
  onReject,
}: {
  approval: PendingApproval;
  selectedActions: string[];
  isSubmitting: boolean;
  onToggleAction: (actionName: string) => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <section className="workbench-card approval-card">
      <div className="card-header">
        <div>
          <span className="section-kicker">Approval Needed</span>
          <h2 className="section-title">Approve proposed actions</h2>
        </div>
        <p className="card-meta">Requested {formatTimestamp(approval.requested_at)}</p>
      </div>

      <p className="section-copy">{approval.context_summary}</p>

      <div className="approval-list">
        {approval.proposals.map((proposal) => {
          const isSelected = selectedActions.includes(proposal.action_name);

          return (
            <label key={proposal.action_name} className="approval-choice">
              <div className="choice-head">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggleAction(proposal.action_name)}
                  disabled={isSubmitting}
                />
                <div className="choice-copy">
                  <strong>{humanize(proposal.action_name)}</strong>
                  <p>{proposal.rationale || "No additional rationale provided."}</p>
                </div>
              </div>
              <p className="choice-impact">
                Potential impact: {proposal.estimated_impact || "Impact not provided."}
              </p>
            </label>
          );
        })}
      </div>

      <div className="button-row">
        <button
          className="primary-button"
          type="button"
          onClick={onApprove}
          disabled={isSubmitting || selectedActions.length === 0}
        >
          {isSubmitting
            ? "Sending..."
            : `Approve ${selectedActions.length} Action${selectedActions.length === 1 ? "" : "s"}`}
        </button>
        <button
          className="secondary-button"
          type="button"
          onClick={onReject}
          disabled={isSubmitting}
        >
          Skip Actions
        </button>
      </div>
    </section>
  );
}

function FinalReportPanel({ report }: { report: FinalReport }) {
  const reportKind = inferReportKind(report);
  const actionSummaries = (report.actions_taken ?? [])
    .map((action) => {
      const label = describeAction(action);
      return label ? { key: `${action.action_name}-${action.status}`, label } : null;
    })
    .filter((action): action is { key: string; label: string } => action !== null);
  const hasFailedActions = (report.actions_taken ?? []).some((action) => action.status === "failed");
  const showInventoryTable = Boolean(report.inventory_items?.length)
    && (reportKind === "inventory_list" || reportKind === "action_confirmation");
  const inventoryItems = sortInventoryItems(report.inventory_items ?? []);
  const presentation = {
    analysis: { kicker: "Answer", title: "What I found" },
    inventory_list: { kicker: "Inventory", title: "Current inventory" },
    action_confirmation: { kicker: "Action Result", title: "What changed" },
    history_response: { kicker: "History", title: "What you've asked before" },
    out_of_scope: { kicker: "Scope", title: "What I can help with" },
  }[reportKind];
  const inventorySectionTitle = reportKind === "action_confirmation" ? "Updated inventory item" : "Inventory items";
  const recommendationsTitle = reportKind === "out_of_scope" ? "Try one of these instead" : "Recommended next steps";
  const actionsSectionTitle = hasFailedActions
    ? "Action results"
    : reportKind === "action_confirmation"
      ? "Action completed"
      : "Actions completed";

  return (
    <section className="workbench-card answer-card">
      <div className="card-header">
        <div>
          <span className="section-kicker">{presentation.kicker}</span>
          <h2 className="section-title">{presentation.title}</h2>
        </div>
      </div>

      <div className="answer-summary">
        <p>{report.executive_summary}</p>
      </div>

      {showInventoryTable ? (
        <section className="answer-section">
          <h3>{inventorySectionTitle}</h3>
          <div className="inventory-table-shell">
            <table className="inventory-table">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">SKU</th>
                  <th scope="col">Available</th>
                  <th scope="col">Reorder point</th>
                  <th scope="col">Status</th>
                  <th scope="col">Base price</th>
                  <th scope="col">Effective price</th>
                  <th scope="col">Discount</th>
                  <th scope="col">Days until stockout</th>
                </tr>
              </thead>
              <tbody>
                {inventoryItems.map((item) => (
                  <tr key={item.product_id}>
                    <td>{item.product_name}</td>
                    <td>{item.product_id}</td>
                    <td>{item.quantity_available}</td>
                    <td>{item.reorder_point}</td>
                    <td>{humanize(item.status)}</td>
                    <td>{formatCurrencyValue(item.unit_price, item.currency)}</td>
                    <td>{formatCurrencyValue(item.effective_price, item.currency)}</td>
                    <td>{describeDiscount(item)}</td>
                    <td>{formatStockoutDays(item.days_until_stockout)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {reportKind === "analysis" && report.analysis?.primary_root_cause ? (
        <section className="answer-section highlight-section">
          <h3>Most likely root cause</h3>
          <p>{report.analysis.primary_root_cause}</p>
        </section>
      ) : null}

      {reportKind === "analysis" && report.analysis?.contributing_factors?.length ? (
        <section className="answer-section">
          <h3>What likely contributed</h3>
          <ul className="list-reset answer-list">
            {report.analysis.contributing_factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {reportKind === "analysis" && report.analysis?.findings?.length ? (
        <section className="answer-section">
          <h3>Key findings</h3>
          <div className="finding-grid">
            {report.analysis.findings.map((finding) => (
              <article
                key={`${finding.domain}-${finding.summary}`}
                className="finding-card"
              >
                <strong>{humanize(finding.domain)}</strong>
                <p>{finding.summary}</p>
                {finding.anomalies?.length ? (
                  <p className="finding-detail">
                    Flagged issue: {finding.anomalies.join(" ")}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {report.recommendations.length ? (
        <section className="answer-section">
          <h3>{recommendationsTitle}</h3>
          <ul className="list-reset answer-list">
            {report.recommendations.map((recommendation) => (
              <li key={recommendation}>{recommendation}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {actionSummaries.length ? (
        <section className="answer-section">
          <h3>{actionsSectionTitle}</h3>
          <ul className="list-reset answer-list">
            {actionSummaries.map((action) => (
              <li key={action.key}>{action.label}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {report.data_gaps.length ? (
        <section className="answer-section">
          <h3>Still worth checking</h3>
          <ul className="list-reset answer-list">
            {report.data_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}

export function StoreOwnerWorkbench() {
  const [draftQuery, setDraftQuery] = useState(SAMPLE_PROMPTS[0]);
  const [dateStr, setDateStr] = useState(todayDateString);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [selectedActions, setSelectedActions] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResolvingApproval, setIsResolvingApproval] = useState(false);

  async function refreshRun(runId: string) {
    try {
      const nextStatus = await readJson<RunStatus>(`/api/query/${runId}/status`);
      startTransition(() => {
        setStatus(nextStatus);
        setError(null);
        if (nextStatus.status !== "pending_approval") {
          setPendingApproval(null);
          setSelectedActions([]);
        }
      });
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  useEffect(() => {
    if (!activeRunId || !status || !POLLING_STATUSES.has(status.status)) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const nextStatus = await readJson<RunStatus>(`/api/query/${activeRunId}/status`);
        if (cancelled) {
          return;
        }

        startTransition(() => {
          setStatus(nextStatus);
          setError(null);
          if (nextStatus.status !== "pending_approval") {
            setPendingApproval(null);
            setSelectedActions([]);
          }
        });
      } catch (requestError) {
        if (!cancelled) {
          setError(errorMessage(requestError));
        }
      }
    };

    const intervalId = window.setInterval(() => {
      void poll();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeRunId, status]);

  useEffect(() => {
    if (!activeRunId || status?.status !== "pending_approval") {
      return;
    }

    let cancelled = false;

    const loadApproval = async () => {
      try {
        const approval = await readJson<PendingApproval>(`/api/actions/${activeRunId}/pending`);
        if (cancelled) {
          return;
        }

        startTransition(() => {
          setPendingApproval(approval);
          setSelectedActions((current) => {
            if (current.length) {
              const validNames = new Set(
                approval.proposals.map((proposal) => proposal.action_name),
              );
              return current.filter((actionName) => validNames.has(actionName));
            }

            return approval.proposals.map((proposal) => proposal.action_name);
          });
          setError(null);
        });
      } catch (requestError) {
        if (!cancelled) {
          setError(errorMessage(requestError));
        }
      }
    };

    void loadApproval();

    return () => {
      cancelled = true;
    };
  }, [activeRunId, status?.status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = draftQuery.trim();
    if (!trimmedQuery) {
      setError("Enter a store question before starting the investigation.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    try {
      const response = await readJson<QueryResponse>("/api/query", {
        method: "POST",
        body: JSON.stringify({
          query: trimmedQuery,
          user_id: DEFAULT_USER_ID,
          date_str: dateStr,
        }),
      });

      startTransition(() => {
        setActiveRunId(response.run_id);
        setSubmittedQuery(trimmedQuery);
        setStatus({
          run_id: response.run_id,
          status: response.status,
          updated_at: new Date().toISOString(),
        });
        setPendingApproval(null);
        setSelectedActions([]);
        setMessage("Investigation started. I’ll bring the answer back here as soon as it’s ready.");
      });
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsSubmitting(false);
    }
  }

  function toggleActionSelection(actionName: string) {
    setSelectedActions((current) =>
      current.includes(actionName)
        ? current.filter((name) => name !== actionName)
        : [...current, actionName],
    );
  }

  async function handleApprovalDecision(
    endpoint: string,
    payload: Record<string, unknown>,
    successMessage: (response: ApprovalDecisionResponse) => string,
  ) {
    if (!activeRunId) {
      return;
    }

    setIsResolvingApproval(true);
    setError(null);
    setMessage(null);

    try {
      const response = await readJson<ApprovalDecisionResponse>(endpoint, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      startTransition(() => {
        setPendingApproval(null);
        setSelectedActions([]);
        setMessage(successMessage(response));
      });

      await refreshRun(activeRunId);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsResolvingApproval(false);
    }
  }

  async function handleApprove() {
    await handleApprovalDecision(
      `/api/actions/${activeRunId}/approve`,
      { approved_action_names: selectedActions },
      () => "Approved actions are now running. I’m finishing the answer.",
    );
  }

  async function handleReject() {
    await handleApprovalDecision(
      `/api/actions/${activeRunId}/reject`,
      { reason: "" },
      () => "Skipped the suggested actions. I’m finalizing the answer.",
    );
  }

  const report = status?.final_report ?? null;
  const displayError =
    status?.status === "failed"
      ? status.error ?? error ?? "The investigation could not be completed."
      : status?.error ?? error;

  return (
    <section className="simple-workbench">
      <section className="workbench-card query-card">
        <div className="card-header">
          <div>
            <span className="section-kicker">Ask A Question</span>
            <h2 className="section-title">What do you want explained about your store?</h2>
          </div>
          <p className="card-meta">
            Describe the issue in plain language and I’ll turn it into a clear answer with next steps.
          </p>
        </div>

        <form className="query-form" onSubmit={handleSubmit}>
          <label className="field-shell" htmlFor="store-query">
            <span>Your question</span>
            <textarea
              id="store-query"
              className="question-input"
              value={draftQuery}
              onChange={(event) => setDraftQuery(event.target.value)}
              placeholder="Describe the issue, when it started, and what impact you want explained."
            />
          </label>

          <div className="query-footer">
            <label className="field-shell date-field">
              <span>Business date</span>
              <input
                className="text-input"
                type="date"
                value={dateStr}
                onChange={(event) => setDateStr(event.target.value)}
              />
            </label>

            <div className="button-row">
              <button className="primary-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Starting..." : "Analyze Store"}
              </button>
            </div>
          </div>

          <div className="prompt-row">
            {SAMPLE_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                className="prompt-chip"
                type="button"
                onClick={() => setDraftQuery(prompt)}
                disabled={isSubmitting}
              >
                {prompt}
              </button>
            ))}
          </div>
        </form>
      </section>

      <div className="result-stack">
        {submittedQuery ? (
          <section className="workbench-card question-card">
            <span className="section-kicker">You Asked</span>
            <p>{submittedQuery}</p>
          </section>
        ) : (
          <section className="workbench-card placeholder-card">
            <span className="section-kicker">What Works Best</span>
            <h2 className="section-title">Ask for the business answer you actually need</h2>
            <ul className="list-reset placeholder-list">
              <li>Call out the metric or behavior that changed.</li>
              <li>Mention the timeframe or event you think caused it.</li>
              <li>Ask for next steps if you want recommendations, not just diagnosis.</li>
            </ul>
          </section>
        )}

        {message ? <div className="notice-banner">{message}</div> : null}
        {displayError ? <div className="error-banner">{displayError}</div> : null}

        {status && !report && !pendingApproval && status.status !== "failed" ? (
          <section className="workbench-card status-card">
            <div className="status-heading">
              <span className="status-dot" aria-hidden="true" />
              <div>
                <span className="section-kicker">In Progress</span>
                <h2 className="section-title">I’m investigating this now</h2>
              </div>
            </div>
            <p className="section-copy">
              I’m pulling together the relevant signals and will replace this with a final answer as soon as the investigation finishes.
            </p>
            <p className="card-meta">Last updated {formatTimestamp(status.updated_at)}</p>
          </section>
        ) : null}

        {pendingApproval ? (
          <ApprovalPanel
            approval={pendingApproval}
            selectedActions={selectedActions}
            isSubmitting={isResolvingApproval}
            onToggleAction={toggleActionSelection}
            onApprove={() => void handleApprove()}
            onReject={() => void handleReject()}
          />
        ) : null}

        {report ? <FinalReportPanel report={report} /> : null}
      </div>
    </section>
  );
}