import { NextResponse } from "next/server";

import {
  getServerBackendConnection,
  submitQuery,
  toErrorResponse,
  type QueryRequest,
} from "@eob/api-client";

export async function POST(request: Request) {
  let payload: QueryRequest;

  try {
    payload = (await request.json()) as QueryRequest;
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body." }, { status: 400 });
  }

  if (!payload.query?.trim()) {
    return NextResponse.json({ detail: "Query is required." }, { status: 400 });
  }

  try {
    const response = await submitQuery(getServerBackendConnection(process.env), {
      ...payload,
      query: payload.query.trim(),
    });
    return NextResponse.json(response);
  } catch (error) {
    const { status, body } = toErrorResponse(error);
    return NextResponse.json(body, { status });
  }
}