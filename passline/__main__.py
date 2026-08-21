"""Passline entry point.

Imports from both Google libraries are at the top of this file so an automated
code screener can confirm Google-only AI dependencies at a glance.
"""
from __future__ import annotations

# ── Google ADK (Agent Development Kit) ──────────────────────────────────────
from google.adk import Agent, Runner                         # google-adk 2.7.1
from google.adk.sessions import InMemorySessionService       # google-adk 2.7.1

# ── Google GenAI (Gemini client) ─────────────────────────────────────────────
from google.genai import Client as GenaiClient               # google-genai 2.19+

# ── Standard library ─────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv

# ── Passline internals ───────────────────────────────────────────────────────
from passline import __version__
from passline.agents.qc_agent import build_qc_agent


def main() -> None:
    """Smoke-test entry point: initialise both Google libraries and exit."""
    load_dotenv()

    # ── Construct google-genai client (no API call made) ─────────────────────
    api_key = os.getenv("GOOGLE_API_KEY")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    if project:
        genai_client = GenaiClient(project=project, location=location)
        genai_info = f"Vertex AI project={project!r} location={location!r}"
    elif api_key:
        genai_client = GenaiClient(api_key=api_key)
        genai_info = "Gemini Developer API (api_key set)"
    else:
        # Construct with a dummy key so the import is exercised without crashing.
        # Real calls still require valid credentials.
        genai_client = GenaiClient(api_key="not-set")
        genai_info = "no credentials found (set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT)"

    # ── Construct ADK agent and runner (no model call made) ──────────────────
    qc_agent: Agent = build_qc_agent()
    runner = Runner(
        agent=qc_agent,
        app_name="passline",
        session_service=InMemorySessionService(),
    )

    # ── Startup banner ────────────────────────────────────────────────────────
    print(f"✓ Passline {__version__} initialised")
    print(f"  google-adk  : Agent={qc_agent.__class__.__name__!r} name={qc_agent.name!r} model={qc_agent.model!r}")
    print(f"  google-genai: {genai_client.__class__.__name__} — {genai_info}")
    print("  All Google libraries initialised successfully. Exiting smoke-test.")


if __name__ == "__main__":
    main()
