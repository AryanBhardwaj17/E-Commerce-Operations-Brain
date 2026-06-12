import { NextResponse } from "next/server";

import {
  getServerBackendConnection,
  rejectActions,
  toErrorResponse,
  type RejectActionsRequest,
} from "@eob/api-client";

export async function POST(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  let payload: RejectActionsRequest;

  try {
    payload = (await request.json()) as RejectActionsRequest;
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body." }, { status: 400 });
  }

  try {
    const { runId } = await context.params;
    const response = await rejectActions(
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