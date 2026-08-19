import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET() {
  const res = await fetch(`${BACKEND_URL}/api/prediction_accuracy`)
  return NextResponse.json(await res.json(), { status: res.status })
}
