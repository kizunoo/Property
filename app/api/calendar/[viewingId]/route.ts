import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ viewingId: string }> | { viewingId: string } }
) {
  try {
    const resolvedParams = await params;
    const rawViewingId = resolvedParams.viewingId;
    const cleanViewingId = rawViewingId ? rawViewingId.replace(/\.ics$/i, "") : "";
    const token = req.nextUrl.searchParams.get("token") || "";
    const expires = req.nextUrl.searchParams.get("expires") || "";

    const clientIp = req.headers.get("x-forwarded-for") || req.headers.get("x-real-ip") || "";

    const upstreamUrl = `${FASTAPI_URL}/api/calendar/${cleanViewingId}.ics?token=${encodeURIComponent(token)}&expires=${encodeURIComponent(expires)}`;
    const upstream = await fetch(upstreamUrl, {
      headers: {
        "X-Forwarded-For": clientIp,
      },
    });

    if (!upstream.ok) {
      const err = await upstream.json().catch(() => ({}));
      return NextResponse.json(
        { error: err?.detail || "Calendar download failed" },
        { status: upstream.status }
      );
    }

    const icsContent = await upstream.text();
    return new NextResponse(icsContent, {
      status: 200,
      headers: {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": upstream.headers.get("Content-Disposition") || `attachment; filename="viewing_${cleanViewingId}.ics"`,
        "Cache-Control": "no-cache",
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || "Failed to download calendar file" },
      { status: 502 }
    );
  }
}
