#!/usr/bin/env python3
"""
Copilot / triage doctor. Finds out EXACTLY why the AI features fail and says it in plain words,
so nobody has to guess or copy logs around.

Run from the project root:
    backend\\venv\\Scripts\\python scripts\\copilot_doctor.py

It never prints secrets (key values are redacted from every line of output).
It reads data like the copilot would (as an admin), so run it on your own machine only.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except ImportError:
    pass

SECRETS = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY",
           "PORTAL_CODE_PEPPER", "GROQ_API_KEY")

HINTS = [
    (("api key not valid", "api_key_invalid", "invalid api key", "api key expired"),
     "The Gemini key is rejected. Create a new key in Google AI Studio and put it in "
     "backend/.env as GOOGLE_API_KEY=... (no quotes, no spaces), then restart the backend."),
    (("missing key inputs", "no api key", "api key must be set", "could not find api key", "no gemini key"),
     "No Gemini key was found. Add GOOGLE_API_KEY=... to backend/.env and restart the backend."),
    (("permission_denied", "403"),
     "The key is valid but not allowed to use this model or API. In Google AI Studio, check the "
     "key's project has the Generative Language API enabled."),
    (("not_found", "404", "is not found for api version", "not supported for generatecontent"),
     "That model name isn't available to your key. Set COPILOT_MODEL=<a model listed in Google "
     "AI Studio> in backend/.env and restart."),
    (("resource_exhausted", "429", "quota", "rate limit"),
     "You hit the Gemini usage limit. Wait a minute and retry, or enable billing on the project."),
    (("no module named", "modulenotfounderror", "importerror"),
     "A Python package is missing. Run: backend\\venv\\Scripts\\pip install -r backend\\requirements.txt"),
    (("timeout", "timed out"),
     "The model call timed out. Check your internet connection and retry."),
]


def redact(text) -> str:
    s = str(text)
    for name in SECRETS:
        v = os.getenv(name)
        if v and len(v) >= 8:
            s = s.replace(v, "***")
    return s


def hint(err) -> str:
    e = redact(err).lower()
    for needles, message in HINTS:
        if any(n in e for n in needles):
            return message
    return "Unrecognised error. Send me the 'ERROR' line above exactly as printed."


RESULTS: list[tuple[str, object, str]] = []  # ok is True / False / "skip"


def _passed(name: str) -> bool:
    return any(n == name and ok is True for n, ok, _ in RESULTS)


def step(name: str, requires: tuple = ()):
    def deco(fn):
        print(f"\n[{len(RESULTS) + 1}] {name}")
        missing = [r for r in requires if not _passed(r)]
        if missing:
            print(f"    SKIPPED (needs a passing: {missing[0]})")
            RESULTS.append((name, "skip", ""))
            return fn
        try:
            detail = fn()
            print(f"    PASS  {redact(detail)}")
            RESULTS.append((name, True, ""))
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {redact(e)}"
            print(f"    FAIL")
            print(f"    ERROR: {msg[:600]}")
            print(f"    MEANING: {hint(msg)}")
            RESULTS.append((name, False, msg))
        return fn
    return deco


def main() -> int:
    print("=== Copilot / triage doctor ===")

    @step("Environment variables (True = set)")
    def _env():
        key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        pepper = bool(os.getenv("PORTAL_CODE_PEPPER"))
        out = (f"GOOGLE_API_KEY/GEMINI_API_KEY={key}  PORTAL_CODE_PEPPER={pepper}  "
               f"ENVIRONMENT={os.getenv('ENVIRONMENT', '(unset)')}")
        if not key:
            raise RuntimeError("No Gemini key found. " + out)
        if not pepper:
            print("    NOTE  PORTAL_CODE_PEPPER is not set: portal login/invites will fail until you add it.")
        return out

    state = {}

    @step("Load the copilot module (ADK installed and importable)")
    def _import():
        import copilot_agent
        state["agent"] = copilot_agent
        return f"ok, model = {copilot_agent.MODEL}"

    @step("Call the Gemini model directly with a tiny prompt (tests key + model only)",
          requires=("Environment variables (True = set)", "Load the copilot module (ADK installed and importable)"))
    def _raw():
        from google import genai
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        reply = genai.Client(api_key=key).models.generate_content(
            model=state["agent"].MODEL, contents="Reply with the single word OK.")
        return f"model said: {(reply.text or '').strip()[:60]!r}"

    @step("Run the real copilot end to end (ADK + tools + your database)",
          requires=("Call the Gemini model directly with a tiny prompt (tests key + model only)",))
    def _copilot():
        text = asyncio.run(state["agent"].run_copilot(
            "doctor", True, "doctor-conversation-1",
            "Who are my top 3 priority clients? One short line each."))
        if not text or text.startswith("I couldn't"):
            raise RuntimeError("The agent returned no answer")
        return "answered: " + text.strip().replace("\n", " | ")[:400]

    @step("Run the inquiry triage agent on a sample message",
          requires=("Call the Gemini model directly with a tiny prompt (tests key + model only)",))
    def _triage():
        import main as app_main
        import triage_agent
        import triage_service
        sb = app_main.supabase
        triage_service.set_db(sb)
        rows = sb.table("clients").select("id").eq("data_source", "real").limit(1).execute().data
        if not rows:
            rows = sb.table("clients").select("id").limit(1).execute().data
        result = triage_agent.run_triage_sync(
            rows[0]["id"], "How much is the cleaning robot? We need a quote ASAP.")
        if result is None:
            raise RuntimeError("The model replied, but not in the required JSON format")
        return f"category={result.category} time_sensitive={result.time_sensitive}"

    print("\n=== Summary ===")
    for name, ok, _ in RESULTS:
        print(f"  {'PASS' if ok is True else 'SKIP' if ok == 'skip' else 'FAIL'}  {name}")
    failed = [r for r in RESULTS if r[1] is False]
    if failed:
        print("\nFix the FIRST failing step above (later ones usually fail because of it), "
              "then run this again.")
        return 1
    print("\nAll good: the copilot and triage AI both work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
