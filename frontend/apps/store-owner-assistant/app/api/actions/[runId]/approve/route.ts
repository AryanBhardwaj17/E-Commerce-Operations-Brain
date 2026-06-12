import { NextResponse } from "next/server";

import {
  approveActions,
  getServerBackendConnection,
  toErrorResponse,
  type ApproveActionsRequest,
} from "@eob/api-client";

export async function POST(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  let payload: ApproveActionsRequest;

  try {
    payload = (await request.json()) as ApproveActionsRequest;
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body." }, { status: 400 });
  }

  if (!Array.isArray(payload.approved_action_names)) {
    return NextResponse.json(
      { detail: "approved_action_names must be an array." },
      { status: 400 },
    );
  }

  try {
    const { runId } = await context.params;
    const response = await approveActions(
      getServerBackendConnection(process.env),
      runId,
      payload,
    );
    return NextResponse.json(response);
  } catch (error) {
    const { status, body } = toErrorResponse(error);
    return NextResponse.json(body, { status });
  }
}