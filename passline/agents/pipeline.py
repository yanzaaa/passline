"""Passline agent pipeline builder.

Assembles the full ADK agent graph:

    SequentialAgent (delivery_pipeline)
    ├── IngestAgent               Stage 1: parse SRT bytes
    ├── ParallelAgent             Stage 2: concurrent checkers
    │   ├── TimingCheckerAgent
    │   ├── FormatCheckerAgent
    │   └── LanguageCheckerAgent  (BaseAgent, calls Gemini directly)
    ├── FindingsMergerAgent       Stage 2b: merge all findings → all_findings
    ├── LoopAgent (max 3 passes)  Stage 3: repair–verify cycle
    │   ├── FixerAgent            (LLM for language-level fixes only)
    │   └── VerifierAgent
    └── ReporterAgent             Stage 4: final report + write_srt

Uses the classic template workflow agents (SequentialAgent / ParallelAgent /
LoopAgent), not the graph workflow API.
"""
from __future__ import annotations

from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent

from passline.agents.ingest_agent import IngestAgent
from passline.agents.timing_checker import TimingCheckerAgent
from passline.agents.format_checker import FormatCheckerAgent
from passline.agents.language_checker import build_language_checker
from passline.agents.findings_merger import FindingsMergerAgent
from passline.agents.fixer_agent import build_fixer_agent
from passline.agents.verifier_agent import VerifierAgent
from passline.agents.reporter_agent import ReporterAgent
from passline.events.bus import EventBus
from passline.pipeline.approval import ApprovalQueue


def build_pipeline(bus: EventBus, approval_queue: ApprovalQueue) -> SequentialAgent:
    """Build and return the full delivery pipeline as a ``SequentialAgent``.

    Parameters
    ----------
    bus:
        Shared event bus for lifecycle events.
    approval_queue:
        Shared approval queue for meaning-changing edits.
    """

    # Stage 1 — Ingest
    ingest = IngestAgent(name="ingest", bus=bus)

    # Stage 2 — Parallel fan-out
    timing_checker = TimingCheckerAgent(name="timing_checker", bus=bus)
    format_checker = FormatCheckerAgent(name="format_checker", bus=bus)
    language_checker = build_language_checker(bus=bus)

    checker_fanout = ParallelAgent(
        name="checker_fanout",
        sub_agents=[timing_checker, format_checker, language_checker],
        description="Concurrent timing, format, and language checks",
    )

    # Stage 2b — Merge all checker findings into all_findings
    findings_merger = FindingsMergerAgent(name="findings_merger")

    # Stage 3 — Repair loop (max 3 passes)
    fixer = build_fixer_agent(bus=bus, approval_queue=approval_queue)
    verifier = VerifierAgent(name="verifier", bus=bus)

    repair_loop = LoopAgent(
        name="repair_loop",
        sub_agents=[fixer, verifier],
        max_iterations=3,
        description="Repair–verify cycle, exits when zero violations or 3 passes done",
    )

    # Stage 4 — Reporter
    reporter = ReporterAgent(name="reporter", bus=bus)

    # Full pipeline
    return SequentialAgent(
        name="delivery_pipeline",
        sub_agents=[ingest, checker_fanout, findings_merger, repair_loop, reporter],
        description="End-to-end subtitle QC and repair pipeline",
    )
