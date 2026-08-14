import { NextRequest, NextResponse } from "next/server";

export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } | Promise<{ id: string }> }
) {
  const resolvedParams = await params;
  const backendUrl = process.env.BACKEND_URL || process.env.FASTAPI_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${backendUrl}/api/signals/${resolvedParams.id}/dismiss`, {
      method: "POST",
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to dismiss signal" },
      { status: 500 }
    );
  }
}
