import { NextResponse } from "next/server";

import {
  getQueryEvents,
  getServerBackendConnection,
  toErrorResponse,
} from "@eob/api-client";

export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  try {
    const { runId } = await context.params;
    const response = await getQueryEvents(
      getServerBackendConnection(process.env),
      runId,
    );
    return NextResponse.json(response);
  } catch (error) {
    const { status, body } = toErrorResponse(error);
    return NextResponse.json(body, { status });
  }
}