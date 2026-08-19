import os
from hashlib import md5
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from groq import Groq
from scoring_engine import score as score_pair

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def check_and_log_tier_signal(client_id: str, client_name: str, new_tier: str, property_id: str = None):
    """
    Compares new_tier against clients.last_known_tier.
    Inserts a signal row if the tier changed, then updates last_known_tier.
    Call this every time a client's tier is recomputed (run_evaluations AND log_viewing).
    """
    client_row = supabase.table("clients").select("last_known_tier").eq("id", client_id).single().execute()
    old_tier = client_row.data.get("last_known_tier") if client_row.data else None

    if old_tier != new_tier:
        if old_tier is None:
            pass  # first evaluation ever for this client — do not fire a signal, nothing to compare against
        elif new_tier == "TIER_1" and old_tier != "TIER_1":
            supabase.table("signals").insert({
                "type": "first_vip",
                "client_id": client_id,
                "property_id": property_id,
                "message": f"{client_name} just crossed into VIP for the first time"
            }).execute()
        else:
            tier_rank = {"TIER_3": 0, "TIER_2": 1, "TIER_1": 2}
            if tier_rank.get(new_tier, 0) > tier_rank.get(old_tier, 0):
                label = {"TIER_1": "VIP", "TIER_2": "WARM", "TIER_3": "COLD"}
                supabase.table("signals").insert({
                    "type": "tier_upgrade",
                    "client_id": client_id,
                    "property_id": property_id,
                    "message": f"{client_name} moved {label.get(old_tier)} → {label.get(new_tier)}"
                }).execute()

        supabase.table("clients").update({"last_known_tier": new_tier}).eq("id", client_id).execute()


app = FastAPI(title="PIPELINE.EV Logic Engine")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
def health_check():
    return {"status": "ok", "service": "PIPELINE.EV Logic Engine"}


@app.post("/api/run_evaluations")
def run_evaluations():
    try:
        clients_response = supabase.table("clients").select("*").execute()
        properties_response = supabase.table("properties").select("*").execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    clients = clients_response.data or []
    properties = properties_response.data or []

    if not clients or not properties:
        raise HTTPException(
            status_code=400,
            detail="Clients and properties tables must contain data before running evaluations.",
        )

    evaluations = []
    for client in clients:
        best_match_tier = None
        best_match_ev = -1
        best_match_property_id = None

        for property_row in properties:
            # Map Supabase field names → canonical ClientProfile shape
            client_profile = {
                "budget":                client.get("stated_budget"),
                "preferred_neighborhood": client.get("preferred_neighborhood"),
                "engagement_history":    client.get("past_viewings"),
                "source":               client.get("source"),
            }

            result = score_pair(client_profile, property_row)

            evaluations.append(
                {
                    "client_id":      client["id"],
                    "property_id":    property_row["id"],
                    "ai_probability": result["probability"],
                    "expected_value": result["expected_value"],
                    "segment_tier":   result["tier"],
                    # confidence is returned but not persisted to the current schema;
                    # remove the next line if the DB column doesn't exist yet.
                    # "confidence":  result["confidence"],
                }
            )

            if result["expected_value"] > best_match_ev:
                best_match_ev = result["expected_value"]
                best_match_tier = result["tier"]
                best_match_property_id = property_row["id"]

        if best_match_tier is not None:
            check_and_log_tier_signal(
                client_id=client["id"],
                client_name=client["name"],
                new_tier=best_match_tier,
                property_id=best_match_property_id
            )


    try:
        result = supabase.table("pipeline_evaluations").upsert(
            evaluations,
            on_conflict="client_id,property_id",
        ).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upsert evaluations: {exc}") from exc

    return {
        "message": "Evaluations completed successfully",
        "count": len(evaluations),
        "evaluations": result.data or evaluations,
    }


# ─── Reasoning endpoint ────────────────────────────────────────────────────────

class ReasoningRequest(BaseModel):
    client_id: str
    property_id: str


def _build_prompt(client: dict, prop: dict) -> str:
    budget = client["stated_budget"]
    prop_val = prop["property_value"]
    financial_fit = budget >= prop_val
    geo_match = client["preferred_neighborhood"] == prop["neighborhood"]
    viewings = client["past_viewings"]

    fin_label = (
        f"✓ budget (RM {budget:,.0f}) covers listing value (RM {prop_val:,.0f})"
        if financial_fit
        else f"✗ budget (RM {budget:,.0f}) is below listing value (RM {prop_val:,.0f})"
    )
    geo_label = (
        f"✓ preferred neighbourhood ({client['preferred_neighborhood']}) matches listing"
        if geo_match
        else f"✗ preferred neighbourhood ({client['preferred_neighborhood']}) does not match listing neighbourhood ({prop['neighborhood']})"
    )
    eng_label = (
        f"{viewings} past viewing(s) recorded — strong engagement signal"
        if viewings > 0
        else "0 past viewings — no prior engagement"
    )

    return f"""You are writing an internal analysis note for a real estate AGENT about their CLIENT — not a message to the client themselves.

CRITICAL PERSPECTIVE RULES:
- Write strictly in the THIRD PERSON, referring to the client by their full name (e.g. "{client['name']}'s budget...", "{client['name']} has viewed...").
- NEVER use second-person pronouns ("you", "your", "for you", "yours"). This is the agent's private analytical reasoning, NOT client-facing copy.

Client profile:
- Name: {client['name']}
- Stated budget: RM {budget:,.0f}
- Preferred neighbourhood: {client['preferred_neighborhood']}
- Past property viewings: {viewings}

Target property:
- Address: {prop['address']}
- Neighbourhood: {prop['neighborhood']}
- Listing value: RM {prop_val:,.0f}

Score breakdown:
- Financial Fit: {fin_label}
- Geo Match: {geo_label}
- Engagement: {eng_label}

Note: This specific target property was selected for this client because it represents their single Highest Expected Value (E(x)) opportunity in the pipeline.

Write a 2-4 sentence internal rationale from the agent's perspective explaining why this property is {client['name']}'s highest-value match opportunity. Explain the trade-off honestly: acknowledge any lower probability or budget stretch if applicable, but justify the match by the potential deal size and expected value to the agent. Do NOT conclude that the property "isn't a strong match" or shouldn't be pursued. Reference their actual budget, neighbourhood preference, and viewing history. Be specific, concise, and professional using Malaysian English conventions. No bullet points or headers. Do not include any preamble — start directly with the client's name."""


def generate_reasoning_text(client_id: str, property_id: str) -> str:
    """
    Core reasoning generator: checks cache, fetches client & property,
    calls Groq LLM, caches result, and returns reasoning string.
    """
    # 1. Try reasoning cache
    try:
        cache_res = (
            supabase.table("reasoning_cache")
            .select("reasoning")
            .eq("client_id", client_id)
            .eq("property_id", property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            return cache_res.data[0]["reasoning"]
    except Exception:
        pass

    # 2. Fetch client + property
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch client/property: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # 3. Call Groq LLM
    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    prompt = _build_prompt(client, prop)

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b",
            temperature=0.4,
            max_tokens=400,
            timeout=20.0,
        )
        reasoning = chat_completion.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    # 4. Persist to reasoning_cache
    try:
        supabase.table("reasoning_cache").upsert(
            {
                "client_id": client_id,
                "property_id": property_id,
                "reasoning": reasoning,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception:
        pass

    return reasoning


@app.post("/api/generate_reasoning")
def generate_reasoning(body: ReasoningRequest):
    # Check cache first for cached flag
    try:
        cache_res = (
            supabase.table("reasoning_cache")
            .select("reasoning")
            .eq("client_id", body.client_id)
            .eq("property_id", body.property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            return {"reasoning": cache_res.data[0]["reasoning"], "cached": True}
    except Exception:
        pass

    reasoning = generate_reasoning_text(body.client_id, body.property_id)
    return {"reasoning": reasoning, "cached": False}


def generate_briefing_line(client_name: str, property_name: str, expected_value: float, probability: float, reasoning_context: str) -> str:
    prompt = (
        f"Based on this analysis: \"{reasoning_context}\" — "
        f"write ONE short, punchy sentence (max 20 words) for a real estate agent's dashboard briefing "
        f"summarizing why {client_name} is a top opportunity for {property_name} "
        f"(P(Buy) {probability*100:.0f}%, expected value RM{expected_value:,.0f}). "
        f"No preamble, no filler, just the single sentence."
    )
    chat_completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        temperature=0.5,
        max_tokens=500,
        timeout=20.0,
    )
    content = chat_completion.choices[0].message.content.strip()
    if not content:
        # Fallback if reasoning model used entire budget on chain of thought
        return f"{client_name} is a prime opportunity for {property_name} with {probability*100:.0f}% buy probability and RM{expected_value:,.0f} expected value."
    return content


@app.get("/api/dashboard_briefing")
def get_dashboard_briefing():
    # Pull top 3 VIP clients by best-match expected_value
    try:
        evals = (
            supabase.table("pipeline_evaluations")
            .select("*, clients(name), properties(address, neighborhood, property_value)")
            .eq("segment_tier", "TIER_1")
            .order("expected_value", desc=True)
            .limit(3)
            .execute()
            .data
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch evaluations: {exc}") from exc

    briefing = []
    for row in (evals or []):
        client_id = row["client_id"]
        property_id = row["property_id"]
        client_info = row.get("clients") or {}
        prop_info = row.get("properties") or {}
        client_name = client_info.get("name", "Unknown Client")
        property_name = prop_info.get("address") or prop_info.get("name", "Unknown Property")
        expected_val = float(row.get("expected_value", 0))
        prob = float(row.get("ai_probability", 0))

        # Check briefing_cache first
        cached_briefing = None
        try:
            b_cache_res = (
                supabase.table("briefing_cache")
                .select("briefing")
                .eq("client_id", client_id)
                .eq("property_id", property_id)
                .limit(1)
                .execute()
            )
            if b_cache_res.data:
                cached_briefing = b_cache_res.data[0]["briefing"]
        except Exception:
            cached_briefing = None

        if cached_briefing:
            briefing_text = cached_briefing
        else:
            reasoning_context = generate_reasoning_text(client_id, property_id)
            briefing_text = generate_briefing_line(
                client_name=client_name,
                property_name=property_name,
                expected_value=expected_val,
                probability=prob,
                reasoning_context=reasoning_context,
            )
            # Try caching in briefing_cache
            try:
                supabase.table("briefing_cache").upsert(
                    {
                        "client_id": client_id,
                        "property_id": property_id,
                        "briefing": briefing_text,
                    },
                    on_conflict="client_id,property_id",
                ).execute()
            except Exception:
                pass

        briefing.append({
            "client_id": client_id,
            "client_name": client_name,
            "property_name": property_name,
            "neighborhood": prop_info.get("neighborhood", ""),
            "expected_value": expected_val,
            "briefing": briefing_text,
            "reasoning": briefing_text,
        })

    return briefing


# ─── Log Viewing endpoint ──────────────────────────────────────────────────────

class LogViewingRequest(BaseModel):
    client_id: str
    property_id: str


@app.post("/api/log_viewing")
def log_viewing(body: LogViewingRequest):
    """
    1. Increment `past_viewings` on the client record by 1.
    2. Re-score just this client-property pair using score_pair().
    3. Upsert the updated evaluation row in pipeline_evaluations.
    4. Return the updated probability, expected_value, and tier.
    """
    # ── 1. Fetch client & property ───────────────────────────────────────────
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", body.client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", body.property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    if not client_res.data:
        raise HTTPException(status_code=404, detail="Client not found")
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # ── 2. Increment past_viewings by 1 ─────────────────────────────────────
    new_viewings = (client.get("past_viewings") or 0) + 1
    try:
        supabase.table("clients").update({"past_viewings": new_viewings}).eq("id", body.client_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update viewings: {exc}") from exc

    # ── 3. Re-score this pair with updated viewings ──────────────────────────
    client_profile = {
        "budget":                 client.get("stated_budget"),
        "preferred_neighborhood": client.get("preferred_neighborhood"),
        "engagement_history":     new_viewings,
        "source":                 client.get("source"),
    }
    result = score_pair(client_profile, prop)
    check_and_log_tier_signal(
        client_id=body.client_id,
        client_name=client["name"],
        new_tier=result["tier"],
        property_id=body.property_id
    )


    # ── 4. Upsert updated evaluation ─────────────────────────────────────────
    try:
        supabase.table("pipeline_evaluations").upsert(
            {
                "client_id":      body.client_id,
                "property_id":    body.property_id,
                "ai_probability": result["probability"],
                "expected_value": result["expected_value"],
                "segment_tier":   result["tier"],
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upsert evaluation: {exc}") from exc

    return {
        "client_id":      body.client_id,
        "client_name":    client.get("name"),
        "property_id":    body.property_id,
        "past_viewings":  new_viewings,
        "probability":    result["probability"],
        "expected_value": result["expected_value"],
        "tier":           result["tier"],
    }


# ─── Schedule Viewing endpoints ────────────────────────────────────────────────

class ScheduleViewingRequest(BaseModel):
    client_id: str
    property_id: str
    scheduled_at: str   # ISO-8601 string from the frontend date+time inputs


@app.post("/api/schedule_viewing")
def schedule_viewing(body: ScheduleViewingRequest):
    """
    Insert a new row into scheduled_viewings (status='upcoming').
    Does NOT touch past_viewings or re-score — that only happens when completed.
    """
    try:
        res = supabase.table("scheduled_viewings").insert({
            "client_id":    body.client_id,
            "property_id":  body.property_id,
            "scheduled_at": body.scheduled_at,
            "status":       "upcoming",
        }).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to schedule viewing: {exc}") from exc

    return {"viewing": res.data[0] if res.data else None}


@app.patch("/api/complete_viewing/{viewing_id}")
def complete_viewing(viewing_id: str):
    """
    Mark a scheduled viewing as completed, then trigger the Log Viewing flow:
    increment past_viewings, re-score, upsert pipeline_evaluations.
    """
    # ── 1. Fetch the scheduled viewing row ──────────────────────────────────
    try:
        view_res = (
            supabase.table("scheduled_viewings")
            .select("*")
            .eq("id", viewing_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch viewing: {exc}") from exc

    if not view_res.data:
        raise HTTPException(status_code=404, detail="Scheduled viewing not found")

    sv = view_res.data[0]
    client_id = sv["client_id"]
    property_id = sv["property_id"]

    # ── 2. Mark scheduled_viewings row as completed ──────────────────────────
    try:
        supabase.table("scheduled_viewings").update({"status": "completed"}).eq("id", viewing_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update viewing status: {exc}") from exc

    # ── 3. Re-use log_viewing logic: increment past_viewings + re-score ──────
    try:
        client_res = supabase.table("clients").select("*").eq("id", client_id).limit(1).execute()
        prop_res   = supabase.table("properties").select("*").eq("id", property_id).limit(1).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch client/property: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop   = prop_res.data[0]

    new_viewings = (client.get("past_viewings") or 0) + 1
    supabase.table("clients").update({"past_viewings": new_viewings}).eq("id", client_id).execute()

    client_profile = {
        "budget":                 client.get("stated_budget"),
        "preferred_neighborhood": client.get("preferred_neighborhood"),
        "engagement_history":     new_viewings,
        "source":                 client.get("source"),
    }
    result = score_pair(client_profile, prop)
    check_and_log_tier_signal(
        client_id=client_id,
        client_name=client["name"],
        new_tier=result["tier"],
        property_id=property_id
    )


    supabase.table("pipeline_evaluations").upsert(
        {
            "client_id":      client_id,
            "property_id":    property_id,
            "ai_probability": result["probability"],
            "expected_value": result["expected_value"],
            "segment_tier":   result["tier"],
        },
        on_conflict="client_id,property_id",
    ).execute()

    return {
        "viewing_id":   viewing_id,
        "client_id":    client_id,
        "client_name":  client.get("name"),
        "property_id":  property_id,
        "past_viewings": new_viewings,
        "probability":  result["probability"],
        "expected_value": result["expected_value"],
        "tier":         result["tier"],
    }


class CancelViewingRequest(BaseModel):
    reason: str | None = "agent"


@app.patch("/api/cancel_viewing/{viewing_id}")
def cancel_viewing(viewing_id: str, body: CancelViewingRequest | None = None):
    """
    Cancel a scheduled viewing. Sets status='cancelled' and records reason if column exists.
    """
    reason = body.reason if (body and body.reason) else "agent"
    db = get_supabase()
    try:
        db.table("scheduled_viewings").update({
            "status": "cancelled",
            "cancellation_reason": reason,
        }).eq("id", viewing_id).execute()
    except Exception:
        try:
            db.table("scheduled_viewings").update({
                "status": "cancelled",
            }).eq("id", viewing_id).execute()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to cancel viewing: {exc}") from exc

    return {"viewing_id": viewing_id, "status": "cancelled", "reason": reason}



@app.get("/api/scheduled_viewings")
def list_scheduled_viewings():
    """
    Fetch all scheduled_viewings rows joined with client + property names.
    Auto-cancels any 'upcoming' viewing scheduled >24 hours in the past.
    """
    db = get_supabase()
    # ── Auto-cancel stale upcoming viewings (> 24 hours past due) ──────────────
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale_res = (
            db.table("scheduled_viewings")
            .select("*, clients(id, name)")
            .eq("status", "upcoming")
            .lt("scheduled_at", cutoff)
            .execute()
        )
        if stale_res.data:
            for viewing in stale_res.data:
                try:
                    db.table("scheduled_viewings").update({
                        "status": "cancelled",
                        "cancellation_reason": "auto_missed",
                    }).eq("id", viewing["id"]).execute()
                except Exception:
                    db.table("scheduled_viewings").update({
                        "status": "cancelled",
                    }).eq("id", viewing["id"]).execute()

                client_obj = viewing.get("clients")
                client_name = client_obj.get("name") if isinstance(client_obj, dict) else "Client"
                supabase.table("signals").insert({
                    "type": "viewing_auto_cancelled",
                    "client_id": viewing["client_id"],
                    "property_id": viewing["property_id"],
                    "message": f"Scheduled viewing for {client_name} auto-cancelled (missed, never marked completed)"
                }).execute()
    except Exception as exc:
        print(f"Auto-cancel check non-fatal error: {exc}")


    try:
        res = (
            db.table("scheduled_viewings")
            .select("*, clients(id, name, preferred_neighborhood), properties(id, address, neighborhood)")
            .order("scheduled_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch scheduled viewings: {exc}") from exc

    return {"viewings": res.data or []}


@app.get("/api/signals")
def get_signals():
    result = supabase.table("signals").select("*").eq("dismissed", False).order("created_at", desc=True).limit(5).execute()
    return result.data


@app.post("/api/signals/{signal_id}/dismiss")
def dismiss_signal(signal_id: str):
    supabase.table("signals").update({"dismissed": True}).eq("id", signal_id).execute()
    return {"success": True}





# ─── Shortlist endpoint ────────────────────────────────────────────────────────

@app.get("/api/shortlist/{property_id}")
def get_shortlist(property_id: str, limit: int = 20):
    """
    Score every client against a specific property using score_pair() and return
    the top `limit` candidates ranked by expected_value descending.
    """
    # ── 1. Fetch property ────────────────────────────────────────────────────
    try:
        prop_res = (
            supabase.table("properties")
            .select("*")
            .eq("id", property_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch property: {exc}") from exc

    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Property not found")

    prop = prop_res.data[0]

    # ── 2. Fetch all clients ─────────────────────────────────────────────────
    try:
        clients_res = supabase.table("clients").select("*").execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch clients: {exc}") from exc

    clients = clients_res.data or []

    # ── 3. Score each client against this property ───────────────────────────
    scored = []
    for client in clients:
        client_profile = {
            "budget":                 client.get("stated_budget"),
            "preferred_neighborhood": client.get("preferred_neighborhood"),
            "engagement_history":     client.get("past_viewings"),
            "source":                 client.get("source"),
        }
        result = score_pair(client_profile, prop)
        scored.append({
            "client_id":      client["id"],
            "name":           client["name"],
            "probability":    result["probability"],
            "tier":           result["tier"],
            "expected_value": result["expected_value"],
            "confidence":     result["confidence"],
        })

    # ── 4. Sort by expected_value desc, cap at limit ─────────────────────────
    scored.sort(key=lambda x: x["expected_value"], reverse=True)
    return scored[:limit]


# ─── Invite generation endpoint ────────────────────────────────────────────────

class InviteRequest(BaseModel):
    client_id: str
    property_id: str
    agent_name: str | None = "R. Delgado"


def _build_invite_prompt(client: dict, prop: dict, agent_name: str = "R. Delgado") -> str:
    budget = client["stated_budget"]
    prop_val = prop["property_value"]
    financial_fit = budget >= prop_val
    geo_match = client["preferred_neighborhood"] == prop["neighborhood"]
    name = agent_name or "R. Delgado"

    return f"""You are senior real estate agent '{name}' representing PIPELINE.EV in Malaysia.

Write a warm, highly professional 3-5 sentence personalized property invitation message to client '{client['name']}'.

Property Details:
- Address: {prop['address']} ({prop['neighborhood']})
- Listing Value: RM {prop_val:,.0f}

Client Profile:
- Stated Budget: RM {budget:,.0f}
- Preferred Neighbourhood: {client['preferred_neighborhood']}
- Financial Match: {"Covers full listing price" if financial_fit else "Slightly above stated budget"}
- Neighbourhood Match: {"Exact match to preferred area" if geo_match else "Nearby premium area"}

Guidelines:
- Address the client respectfully by name (e.g., "Dear {client['name']}").
- Explicitly invite them for a private, priority viewing of this specific property.
- Mention why this listing aligns with their profile (referencing their budget capacity and neighbourhood preferences).
- Sign off the invitation with your actual name "{name}" and title ("Senior Agent, PIPELINE.EV").
- NEVER output generic placeholders like "[Your Name]", "[Agent Name]", or "[Your Title]" under any circumstances.
- Do NOT include subject lines or metadata headers — output only the clean, complete message body ready to send."""


@app.post("/api/generate_invite")
def generate_invite(body: InviteRequest):
    agent_name = body.agent_name or "R. Delgado"

    # ── 1. Check invite_drafts cache table first ──────────────────────────────
    try:
        cache_res = (
            supabase.table("invite_drafts")
            .select("draft")
            .eq("client_id", body.client_id)
            .eq("property_id", body.property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            cached_draft = cache_res.data[0]["draft"]
            # Invalidate stale cached draft if it contains generic placeholders
            if "[Your Name]" not in cached_draft and "[Agent Name]" not in cached_draft:
                return {"draft": cached_draft, "cached": True}
    except Exception:
        # invite_drafts table may not exist yet — skip cache, proceed to LLM
        pass

    # ── 2. Fetch client & property ───────────────────────────────────────────
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", body.client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", body.property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # ── 3. Call Groq LLM ─────────────────────────────────────────────────────
    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    prompt = _build_invite_prompt(client, prop, agent_name=agent_name)

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b",
            temperature=0.5,
            max_tokens=500,
            timeout=20.0,
        )
        draft = chat_completion.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    # ── 4. Persist to invite_drafts ──────────────────────────────────────────
    try:
        supabase.table("invite_drafts").upsert(
            {
                "client_id": body.client_id,
                "property_id": body.property_id,
                "draft": draft,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception:
        pass

    return {"draft": draft, "cached": False}


# ─── Analytics Insight endpoint ────────────────────────────────────────────────

class TierSummary(BaseModel):
    tier: str
    count: int
    total_expected_value: float
    avg_probability: float

class InsightRequest(BaseModel):
    total_clients: int
    total_expected_value: float
    avg_probability: float
    tiers: list[TierSummary]
    neighborhoods: list[dict]  # [{"name": str, "count": int, "total_ex": float}]
    active_filters: dict       # {"tier": str, "neighborhood": str}


def _build_insight_prompt(body: InsightRequest) -> str:
    tier_lines = "\n".join(
        f"  - {t.tier.replace('_', ' ')} ({t.tier.replace('TIER_1','VIP').replace('TIER_2','WARM').replace('TIER_3','COLD')}): "
        f"{t.count} clients · avg P(Buy) {round(t.avg_probability * 100)}% · total E(x) RM {t.total_expected_value:,.0f}"
        for t in body.tiers
    )
    top_nbhds = sorted(body.neighborhoods, key=lambda x: x["total_ex"], reverse=True)[:3]
    nbhd_lines = ", ".join(
        f"{n['name']} (RM {n['total_ex']:,.0f})" for n in top_nbhds
    )
    filters_desc = (
        f"Current filter: {body.active_filters.get('tier', 'ALL')} tier"
        + (f" · {body.active_filters.get('neighborhood', '')} neighborhood"
           if body.active_filters.get("neighborhood") and body.active_filters["neighborhood"] != "ALL"
           else "")
    )

    return f"""You are a senior real estate analytics AI for PIPELINE.EV, a Malaysian property investment platform.

Current pipeline snapshot ({filters_desc}):
- Total clients in view: {body.total_clients}
- Total pipeline E(x): RM {body.total_expected_value:,.0f}
- Avg P(Buy) across all: {round(body.avg_probability * 100)}%

Tier breakdown:
{tier_lines}

Top neighborhoods by total E(x): {nbhd_lines if nbhd_lines else "N/A"}

Write exactly 2-3 sentences of actionable insight for an agent reviewing this data. Highlight the most significant pattern (e.g. concentration of VIP value in one area, low conversion from warm to VIP, a neighborhood outperforming others). Be specific with RM figures and percentages. Use Malaysian English. No bullet points, no headers, no preamble — output only the insight sentences."""


@app.post("/api/generate_insight")
def generate_insight(body: InsightRequest):
    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    if body.total_clients == 0:
        return {"insight": "No clients match the current filter — try broadening your selection.", "cached": False}

    prompt = _build_insight_prompt(body)

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b",
            temperature=0.4,
            max_tokens=400,
            timeout=20.0,
        )
        insight = chat_completion.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    return {"insight": insight, "cached": False}


@app.post("/api/generate_chart_insight")
def generate_chart_insight(body: dict):
    slice_type = body.get("slice_type")  # "tier" | "scatter_point" | "heatmap_cell" | "cluster"
    slice_data = body.get("slice_data", {})  # dict of relevant filter values

    cache_key = md5(f"{slice_type}:{sorted(slice_data.items())}".encode()).hexdigest()
    try:
        cached = supabase.table("chart_insight_cache").select("insight").eq("cache_key", cache_key).execute().data
        if cached:
            return {"insight": cached[0]["insight"]}
    except Exception:
        pass

    if slice_type == "tier":
        # Deduplicate to unique clients in this tier (using best-match row per client)
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name)").execute().data or []
        client_best_matches = {}
        for r in rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r

        tier_clients = [r for r in client_best_matches.values() if r.get("segment_tier") == slice_data["tier"]]
        client_count = len(tier_clients)
        total_value = sum(r["expected_value"] for r in tier_clients)

        prompt = (
            f"There are EXACTLY {client_count} {slice_data['tier']} clients in the pipeline, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a client count — do not estimate, round, or invent a different number. "
            f"In one short sentence, explain what this means for an agent's priorities."
        )

    elif slice_type == "scatter_point":
        row_res = supabase.table("pipeline_evaluations").select("*, clients(name), properties(address)").eq("client_id", slice_data["client_id"]).eq("property_id", slice_data["property_id"]).limit(1).execute()
        if not row_res.data:
            raise HTTPException(status_code=404, detail="Evaluation data not found")
        row = row_res.data[0]
        c_name = row.get("clients", {}).get("name", "Client")
        p_name = row.get("properties", {}).get("address", "Property")
        prob_pct = round(float(row.get("ai_probability", 0)) * 100)
        ex_val = float(row.get("expected_value", 0))

        prompt = (
            f"Client {c_name} has an EXACT buy probability of {prob_pct}% and expected value of RM{ex_val:,.0f} for {p_name}. "
            f"You MUST use the exact probability {prob_pct}% if you mention a probability — do not estimate, round, or invent a different figure. "
            f"In one short sentence, explain why {c_name} sits in this position and what action the agent should take."
        )

    elif slice_type == "heatmap_cell":
        # Deduplicate: each client counted once, placed by preferred_neighborhood × overall tier
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name, preferred_neighborhood)").execute().data or []
        client_best_matches = {}
        for r in rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r

        matching = [
            r for r in client_best_matches.values()
            if r.get("segment_tier") == slice_data["tier"]
            and r.get("clients", {}).get("preferred_neighborhood") == slice_data["neighborhood"]
        ]
        client_count = len(matching)
        total_value = sum(r["expected_value"] for r in matching)

        prompt = (
            f"There are EXACTLY {client_count} {slice_data['tier']} clients interested in {slice_data['neighborhood']}, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a client count — do not estimate, round, or invent a different number. "
            f"In one short sentence, explain the significance of this concentration for an agent's outreach strategy."
        )

    elif slice_type == "cluster":
        # Deduplicate to unique clients per neighborhood matching the frontend card calculation
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name, preferred_neighborhood)").execute().data or []
        nbhd_rows = [r for r in rows if r.get("clients", {}).get("preferred_neighborhood") == slice_data["neighborhood"]]
        
        # Take the best-match evaluation row per unique client
        client_best_matches = {}
        for r in nbhd_rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r
                
        unique_matches = list(client_best_matches.values())
        client_count = len(unique_matches)
        total_value = sum(r["expected_value"] for r in unique_matches)

        prompt = (
            f"There are EXACTLY {client_count} clients interested in {slice_data['neighborhood']}, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a client count — do not estimate, round, or invent a different number. "
            f"In one short strategic sentence, advise an agent on their approach to this cluster."
        )

    else:
        raise HTTPException(status_code=400, detail="Unknown slice_type")

    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b",
            temperature=0.4,
            max_tokens=250,
            timeout=20.0,
        )
        insight = chat_completion.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    try:
        supabase.table("chart_insight_cache").insert({"cache_key": cache_key, "insight": insight}).execute()
    except Exception:
        pass

    return {"insight": insight}


# ─── Outcome Tracking ──────────────────────────────────────────────────────────

@app.post("/api/record_outcome")
def record_outcome(body: dict):
    client_id = body.get("client_id")
    property_id = body.get("property_id")
    outcome = body.get("outcome")

    if not client_id or not property_id:
        raise HTTPException(status_code=400, detail="client_id and property_id are required")
    if outcome not in ("won", "lost"):
        raise HTTPException(status_code=400, detail="outcome must be 'won' or 'lost'")

    supabase.table("pipeline_evaluations").update({
        "outcome": outcome,
        "outcome_recorded_at": datetime.now(timezone.utc).isoformat(),
    }).eq("client_id", client_id).eq("property_id", property_id).execute()

    return {"success": True}


@app.get("/api/prediction_accuracy")
def get_prediction_accuracy():
    try:
        rows = supabase.table("pipeline_evaluations").select("*").neq("outcome", "pending").execute().data or []
    except Exception:
        # outcome column doesn't exist yet — return graceful fallback
        return {"total_recorded": 0, "message": "Run the outcome migration in Supabase SQL Editor first"}

    if not rows:
        return {"total_recorded": 0, "message": "No outcomes recorded yet"}

    won = [r for r in rows if r.get("outcome") == "won"]
    lost = [r for r in rows if r.get("outcome") == "lost"]

    avg_prob_won = sum(r["ai_probability"] for r in won) / len(won) if won else 0
    avg_prob_lost = sum(r["ai_probability"] for r in lost) / len(lost) if lost else 0

    return {
        "total_recorded": len(rows),
        "won_count": len(won),
        "lost_count": len(lost),
        "avg_predicted_probability_when_won": round(avg_prob_won * 100, 1),
        "avg_predicted_probability_when_lost": round(avg_prob_lost * 100, 1),
    }
