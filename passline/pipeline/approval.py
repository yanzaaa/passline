"""Human approval queue for meaning-changing subtitle edits.

The queue persists in-memory across requests via a module-level singleton.
Each pending item has an associated ``asyncio.Event`` gate; the repair loop
coroutine suspends on ``await_decision()`` until the human resolves the item
via the dashboard API.

State layout
------------
Each item is an :class:`ApprovalItem` dataclass.  Items move through states::

    pending  ──approve──>  approved
    pending  ──reject───>  rejected

The queue is module-level so it survives across web requests in the same
process.  It does NOT survive process restarts — for the hackathon scope this
is acceptable.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from typing import Literal

log = logging.getLogger(__name__)


@dataclasses.dataclass
class ApprovalItem:
    """One pending human-approval request."""

    item_id: str
    delivery_id: str
    cue_index: int
    original_text: str
    proposed_text: str
    reason: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    rule_ref: str = ""
    confidence: float = 0.0
    explanation: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ApprovalQueue:
    """Multi-item approval queue with asyncio gate per pending item.

    Typical usage in the fixer agent::

        item_id = queue.enqueue(ApprovalItem(...))
        decision = await queue.await_decision(item_id)
        # decision is "approved" or "rejected"
    """

    def __init__(self, bus=None) -> None:
        self._items: dict[str, ApprovalItem] = {}
        self._gates: dict[str, asyncio.Event] = {}
        self._bus = bus  # Optional EventBus for APPROVAL_REQUIRED events

    def set_bus(self, bus) -> None:  # type: ignore[type-arg]
        """Attach an EventBus after construction."""
        self._bus = bus

    def enqueue(self, item: ApprovalItem) -> str:
        """Add *item* to the queue, return its ``item_id``.

        Also emits an ``approval.required`` event so the dashboard card
        activates.
        """
        self._items[item.item_id] = item
        gate = asyncio.Event()
        self._gates[item.item_id] = gate

        log.info(
            "ApprovalQueue: enqueued item_id=%s cue=%d",
            item.item_id,
            item.cue_index,
        )

        if self._bus is not None:
            from passline.events.bus import DeliveryEvent, EventType
            self._bus.emit(DeliveryEvent(
                event_type=EventType.APPROVAL_REQUIRED,
                delivery_id=item.delivery_id,
                language="und",
                details={
                    "item_id": item.item_id,
                    "reason": item.reason,
                    "cue_index": item.cue_index,
                    "original_text": item.original_text,
                    "proposed_text": item.proposed_text,
                    "violation_count": 1,
                },
            ))

        return item.item_id

    def approve(self, item_id: str) -> bool:
        """Approve the pending item with *item_id*.

        Returns True if the item existed and was pending, False otherwise.
        """
        item = self._items.get(item_id)
        if item is None or item.status != "pending":
            return False
        item.status = "approved"
        gate = self._gates.get(item_id)
        if gate is not None:
            gate.set()
        log.info("ApprovalQueue: approved item_id=%s", item_id)
        return True

    def reject(self, item_id: str) -> bool:
        """Reject the pending item with *item_id*.

        Returns True if the item existed and was pending, False otherwise.
        """
        item = self._items.get(item_id)
        if item is None or item.status != "pending":
            return False
        item.status = "rejected"
        gate = self._gates.get(item_id)
        if gate is not None:
            gate.set()
        log.info("ApprovalQueue: rejected item_id=%s", item_id)
        return True

    def pending(self) -> list[ApprovalItem]:
        """Return all items with status 'pending'."""
        return [item for item in self._items.values() if item.status == "pending"]

    def get(self, item_id: str) -> ApprovalItem | None:
        """Return item by ID or None."""
        return self._items.get(item_id)

    async def await_decision(self, item_id: str) -> Literal["approved", "rejected"]:
        """Suspend until the human approves or rejects *item_id*.

        Returns the final status string.  If the item does not exist, returns
        'rejected' immediately.
        """
        gate = self._gates.get(item_id)
        if gate is None:
            log.warning("await_decision: unknown item_id=%s — returning rejected", item_id)
            return "rejected"
        await gate.wait()
        item = self._items[item_id]
        status = item.status
        assert status in ("approved", "rejected")
        return status  # type: ignore[return-value]

    def make_item(
        self,
        *,
        delivery_id: str,
        cue_index: int,
        original_text: str,
        proposed_text: str,
        reason: str,
        rule_ref: str = "",
        confidence: float = 0.0,
        explanation: str = "",
    ) -> ApprovalItem:
        """Convenience factory that auto-generates a UUID item_id."""
        return ApprovalItem(
            item_id=str(uuid.uuid4()),
            delivery_id=delivery_id,
            cue_index=cue_index,
            original_text=original_text,
            proposed_text=proposed_text,
            reason=reason,
            rule_ref=rule_ref,
            confidence=confidence,
            explanation=explanation,
        )


# Module-level singleton shared across all requests in the same process
approval_queue = ApprovalQueue()
