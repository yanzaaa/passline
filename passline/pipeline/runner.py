"""PipelineRunner — wraps the ADK Runner for end-to-end subtitle delivery.

Provides a simple async coroutine interface:

    runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
    report = await runner.run_delivery(srt_bytes, language="en")
    repaired_bytes = await runner.get_repaired_bytes()

Uses ``InMemorySessionService`` — one session per delivery run.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from passline.agents.coordinator import build_coordinator
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.pipeline.approval import ApprovalQueue

log = logging.getLogger(__name__)

_APP_NAME = "passline"


class PipelineRunner:
    """Thin wrapper around the ADK ``Runner`` for subtitle delivery runs.

    Each :meth:`run_delivery` call creates a fresh session so state from one
    delivery does not leak into the next.
    """

    def __init__(self, bus: EventBus, approval_queue: ApprovalQueue) -> None:
        self._bus = bus
        self._approval_queue = approval_queue
        self._session_service = InMemorySessionService()
        self._last_session_id: str | None = None

    def _build_runner(self, is_demo: bool = False) -> Runner:
        if is_demo:
            from passline.agents.pipeline import build_pipeline
            agent = build_pipeline(
                bus=self._bus,
                approval_queue=self._approval_queue,
            )
        else:
            from passline.agents.coordinator import build_coordinator
            agent = build_coordinator(
                bus=self._bus,
                approval_queue=self._approval_queue,
            )
        return Runner(
            agent=agent,
            app_name=_APP_NAME,
            session_service=self._session_service,
            auto_create_session=True,
        )

    async def run_delivery(
        self,
        srt_bytes: bytes,
        language: str = "und",
        delivery_id: str | None = None,
        parent_id: str | None = None,
        is_demo: bool = False,
    ) -> dict[str, Any]:
        """Run the full QC pipeline on *srt_bytes* and return the delivery report.

        Parameters
        ----------
        srt_bytes:
            Raw SRT file bytes.
        language:
            ISO language code (e.g. ``"en"``, ``"fr"``, ``"de"``).
        delivery_id:
            Optional identifier for this delivery run.  Auto-generated if None.
        parent_id:
            Optional identifier for parent delivery.
        is_demo:
            If true, bypass the LLM coordinator.

        Returns
        -------
        dict
            The delivery report as a plain dict.
        """
        delivery_id = delivery_id or str(uuid.uuid4())
        session_id = f"delivery-{delivery_id}"
        self._last_session_id = session_id

        # Wire approval queue bus (in case it was set up after queue creation)
        self._approval_queue.set_bus(self._bus)

        start_details = {"stage": "pipeline_start", "bytes": len(srt_bytes)}
        if parent_id:
            start_details["parent_id"] = parent_id

        # Emit start event
        self._bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id=delivery_id,
            language=language,
            details=start_details,
        ))

        # Pre-populate session state with the input data
        state = {
            "srt_bytes": srt_bytes,
            "language": language,
            "delivery_id": delivery_id,
            "is_demo": is_demo,
        }
        if parent_id:
            state["parent_id"] = parent_id

        await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id="pipeline",
            session_id=session_id,
            state=state,
        )

        runner = self._build_runner(is_demo=is_demo)

        try:
            async for _ev in runner.run_async(
                user_id="pipeline",
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=f"Process subtitle file for delivery {delivery_id}")],
                ),
            ):
                pass  # Events reach the dashboard via the bus; we drain the ADK stream

        except Exception as exc:
            import traceback
            traceback.print_exc()
            log.error("PipelineRunner: delivery %s failed — %s", delivery_id, exc)
            self._bus.emit(DeliveryEvent(
                event_type=EventType.QC_VIOLATION,
                delivery_id=delivery_id,
                language=language,
                details={"verdict": "error", "error": str(exc)},
            ))
            return {"delivery_id": delivery_id, "verdict": "error", "error": str(exc)}

        # Read the report from session state
        session = await self._session_service.get_session(
            app_name=_APP_NAME,
            user_id="pipeline",
            session_id=session_id,
        )
        report: dict = session.state.get("report", {
            "delivery_id": delivery_id,
            "verdict": "unknown",
            "note": "pipeline completed but report not written",
        })
        if "language_findings" in session.state:
            report["language_findings"] = session.state["language_findings"]
        return report

    async def get_repaired_bytes(self, delivery_id: str | None = None) -> bytes | None:
        """Return the repaired SRT bytes for *delivery_id* (or the last run).

        Reads directly from the ADK session state produced by ReporterAgent.
        Returns None if no run has been executed or if the reporter failed.
        Async-safe: does not use ``loop.run_until_complete`` and is safe to
        call from within a running event loop.
        """
        session_id = (
            f"delivery-{delivery_id}" if delivery_id else self._last_session_id
        )
        if session_id is None:
            return None
        try:
            session = await self._session_service.get_session(
                app_name=_APP_NAME,
                user_id="pipeline",
                session_id=session_id,
            )
            if session is None:
                return None
            return session.state.get("repaired_bytes")
        except Exception as exc:
            log.warning("get_repaired_bytes(%s): %s", session_id, exc)
            return None
