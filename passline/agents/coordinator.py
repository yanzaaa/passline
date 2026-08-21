"""Root coordinator agent.

Owns a delivery session and delegates the full QC pipeline via the
``run_pipeline`` tool.  Uses ``gemini-3-flash-preview`` on Vertex AI.

The coordinator:
- Holds NO output_schema (uses tools and session state for data exchange)
- Exposes the pipeline through the same web API routes the dashboard uses
- Wraps invocations with exponential-backoff retry (rate-limit protection)
"""
from __future__ import annotations

import logging
import os

from google.adk import Agent  # LlmAgent public alias
from google.adk.agents.llm_agent import LlmAgent

from passline.agents.callbacks import install_retry_on_model
from passline.agents.pipeline import build_pipeline
from passline.events.bus import EventBus
from passline.pipeline.approval import ApprovalQueue

log = logging.getLogger(__name__)

_DEFAULT_COORDINATOR_MODEL = "gemini-3-flash-preview"
_FALLBACK_MODEL = "gemini-2.5-flash"

_COORDINATOR_INSTRUCTION = """
You are the Passline delivery coordinator managing a subtitle QC pipeline.

Your job is to orchestrate the end-to-end subtitle quality-control and repair
workflow for streaming delivery.

When asked to process a subtitle file, invoke the run_pipeline tool exactly
once.  The pipeline will:
1. Parse the subtitle file
2. Run timing, format, and language checks concurrently
3. Apply repairs (up to 3 passes)
4. Produce a delivery report

After the pipeline completes, report the delivery verdict from the session
state "report" field.  If the verdict is "passed", confirm delivery
authorization.  If "failed", list the remaining violations.

You do NOT perform arithmetic or make language judgments — those are handled
by the specialized sub-agents.
""".strip()


def build_coordinator(bus: EventBus, approval_queue: ApprovalQueue) -> LlmAgent:
    """Build the root coordinator agent.

    Parameters
    ----------
    bus:
        Shared event bus for lifecycle events.
    approval_queue:
        Shared approval queue for meaning-changing edits.
    """
    model = os.getenv("PASSLINE_COORDINATOR_MODEL", _DEFAULT_COORDINATOR_MODEL)

    pipeline = build_pipeline(bus=bus, approval_queue=approval_queue)

    # Expose pipeline as a sub-agent (coordinator delegates to it as a tool)
    coordinator = Agent(
        name="coordinator",
        model=model,
        instruction=_COORDINATOR_INSTRUCTION,
        description="Root delivery coordinator for Passline subtitle QC pipeline",
        sub_agents=[pipeline],
        # No output_schema — coordinator uses tools and session state
    )

    install_retry_on_model(coordinator, max_attempts=4, base_delay_s=1.0)

    return coordinator
