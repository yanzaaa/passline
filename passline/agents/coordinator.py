"""Root coordinator agent.

Delegates the full QC pipeline to the ``delivery_pipeline`` sub-agent via
ADK's ``transfer_to_agent`` mechanism.  Uses ``gemini-3-flash-preview`` on
Vertex AI.

The coordinator:
- Holds NO output_schema (uses tools and session state for data exchange)
- Exposes the pipeline as a sub-agent (ADK delegates via transfer_to_agent)
- Wraps invocations with exponential-backoff retry (rate-limit protection)
- Has an ``after_agent_callback`` that runs the pipeline directly if the LLM
  fails to produce a ``report`` in session state (deterministic fallback)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from google.adk import Agent  # LlmAgent public alias
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.callback_context import CallbackContext

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

When asked to process a subtitle file, transfer control to the sub-agent named
"delivery_pipeline" exactly once.  Use the transfer_to_agent action to do this.
The pipeline will:
1. Parse the subtitle file
2. Run timing, format, and language checks concurrently
3. Merge findings and apply repairs (up to 3 passes)
4. Produce a delivery report in session state under the key "report"

After the pipeline completes, report the delivery verdict from the session
state "report" field.  If the verdict is "passed", confirm delivery
authorization.  If "failed", list the remaining violations.

You do NOT perform arithmetic or make language judgments — those are handled
by the specialized sub-agents.

IMPORTANT: Always transfer to delivery_pipeline. Do not attempt to perform
the pipeline steps yourself. Do not describe what you would do — just
transfer immediately.
""".strip()


def _make_fallback_callback(
    bus: EventBus,
    approval_queue: ApprovalQueue,
) -> Any:
    """Return an ``after_agent_callback`` that runs the pipeline directly if no
    report was produced by the LLM coordinator.

    This guards against the case where the LLM returns prose instead of
    delegating to the pipeline, which would leave ``session.state["report"]``
    empty.
    """
    def after_coordinator(callback_context: CallbackContext) -> None:  # type: ignore[type-arg]
        report = callback_context.state.get("report")
        if report is not None:
            log.debug("coordinator: report already in state — no fallback needed")
            return

        log.warning(
            "coordinator: LLM did not produce a report — running pipeline "
            "directly via deterministic fallback"
        )
        import asyncio
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import InMemorySessionService
        from google.genai import types

        pipeline = build_pipeline(bus=bus, approval_queue=approval_queue)

        async def _run_fallback() -> None:
            svc = InMemorySessionService()
            session_id = "coordinator-fallback"
            await svc.create_session(
                app_name="passline-fallback",
                user_id="fallback",
                session_id=session_id,
                state=dict(callback_context.state),
            )
            runner = Runner(
                agent=pipeline,
                app_name="passline-fallback",
                session_service=svc,
                auto_create_session=True,
            )
            async for _ev in runner.run_async(
                user_id="fallback",
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text="run pipeline")],
                ),
            ):
                pass
            # Copy final state back
            session = await svc.get_session(
                app_name="passline-fallback",
                user_id="fallback",
                session_id=session_id,
            )
            for key, val in session.state.items():
                callback_context.state[key] = val

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context (e.g., FastAPI) — schedule as task
                asyncio.ensure_future(_run_fallback())
            else:
                loop.run_until_complete(_run_fallback())
        except Exception as exc:
            log.error("coordinator fallback failed: %s", exc)

    return after_coordinator


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

    # Expose pipeline as a sub-agent (ADK delegates via transfer_to_agent)
    coordinator = Agent(
        name="coordinator",
        model=model,
        instruction=_COORDINATOR_INSTRUCTION,
        description="Root delivery coordinator for Passline subtitle QC pipeline",
        sub_agents=[pipeline],
        after_agent_callback=_make_fallback_callback(bus, approval_queue),
        # No output_schema — coordinator uses sub-agent delegation and session state
    )

    install_retry_on_model(coordinator, max_attempts=4, base_delay_s=1.0)

    return coordinator
