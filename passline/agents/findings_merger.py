"""FindingsMergerAgent — bookkeeping agent that merges checker findings.

Runs after the parallel checker fan-out and before the repair loop.
Reads ``timing_findings``, ``format_findings``, and ``language_findings``
from session state, merges them into a single deduplicated ``all_findings``
list, and writes the result back.

Deduplication key: ``(cue_index, rule)`` — first occurrence wins.

No LLM involvement. No events emitted (bookkeeping only).
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from pydantic import ConfigDict

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

log = logging.getLogger(__name__)

# Session state keys
STATE_TIMING_FINDINGS = "timing_findings"
STATE_FORMAT_FINDINGS = "format_findings"
STATE_LANGUAGE_FINDINGS = "language_findings"
STATE_ALL_FINDINGS = "all_findings"


class FindingsMergerAgent(BaseAgent):
    """ADK BaseAgent that merges the three checker outputs into ``all_findings``.

    This agent has no bus dependency — it is pure bookkeeping.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        timing = ctx.session.state.get(STATE_TIMING_FINDINGS, []) or []
        fmt = ctx.session.state.get(STATE_FORMAT_FINDINGS, []) or []
        language = ctx.session.state.get(STATE_LANGUAGE_FINDINGS, []) or []

        merged: list[dict] = []
        seen: set[tuple] = set()

        for finding in (*timing, *fmt, *language):
            key = (finding.get("cue_index"), finding.get("rule"))
            if key not in seen:
                seen.add(key)
                merged.append(finding)

        log.debug(
            "FindingsMergerAgent: %d timing + %d format + %d language = %d merged",
            len(timing), len(fmt), len(language), len(merged),
        )

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={STATE_ALL_FINDINGS: merged}),
        )
