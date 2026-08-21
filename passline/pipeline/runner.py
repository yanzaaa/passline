"""PipelineRunner — wraps the ADK Runner for end-to-end subtitle delivery.

Provides a simple async coroutine interface:

    runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
    report = await runner.run_delivery(srt_bytes, language="en")
    repaired_bytes = runner.get_repaired_bytes()

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

    def _build_runner(self) -> Runner:
        coordinator = build_coordinator(
            bus=self._bus,
            approval_queue=self._approval_queue,
        )
        return Runner(
            agent=coordinator,
            app_name=_APP_NAME,
            session_service=self._session_service,
            auto_create_session=True,
        )

    async def run_delivery(
        self,
        srt_bytes: bytes,
        language: str = "und",
        delivery_id: str | None = None,
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

        # Emit start event
        self._bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id=delivery_id,
            language=language,
            details={"stage": "pipeline_start", "bytes": len(srt_bytes)},
        ))

        # Pre-populate session state with the input data
        await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id="pipeline",
            session_id=session_id,
            state={
                "srt_bytes": srt_bytes,
                "language": language,
                "delivery_id": delivery_id,
            },
        )

        runner = self._build_runner()

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
        return report

    def get_repaired_bytes(self) -> bytes | None:
        """Return the repaired SRT bytes from the last delivery run.

        Returns None if no run has been executed or if the reporter failed.
        This is a synchronous helper — call from a sync context after awaiting
        ``run_delivery``.
        """
        if self._last_session_id is None:
            return None
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            session = loop.run_until_complete(
                self._session_service.get_session(
                    app_name=_APP_NAME,
                    user_id="pipeline",
                    session_id=self._last_session_id,
                )
            )
            return session.state.get("repaired_bytes")
        except Exception as exc:
            log.warning("get_repaired_bytes: %s", exc)
            return None
