import { NextResponse } from "next/server";

export async function GET() {
  const backendUrl = process.env.BACKEND_URL || process.env.FASTAPI_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${backendUrl}/api/signals`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch signals" },
      { status: 500 }
    );
  }
}
