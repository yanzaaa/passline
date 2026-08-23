"""Shared helpers for emitting station lifecycle events.

Centralises the ``station.working`` / ``station.ready`` pattern used by all
agents, ensuring the vocabulary matches the demo fixture (``station_id`` /
``station_name`` keys, not the old single-key ``station``).
"""
from __future__ import annotations

from passline.events.bus import DeliveryEvent, EventBus, EventType


def emit_station_working(
    bus: EventBus,
    station_id: str,
    station_name: str,
    delivery_id: str,
    language: str,
    **extra: object,
) -> None:
    """Emit ``station.working`` with the canonical vocabulary."""
    details: dict = {"station_id": station_id, "station_name": station_name, **extra}
    bus.emit(DeliveryEvent(
        event_type=EventType.STATION_WORKING,
        delivery_id=delivery_id,
        language=language,
        details=details,
    ))


def emit_station_ready(
    bus: EventBus,
    station_id: str,
    station_name: str,
    delivery_id: str,
    language: str,
    **extra: object,
) -> None:
    """Emit ``station.ready`` with the canonical vocabulary."""
    details: dict = {"station_id": station_id, "station_name": station_name, **extra}
    bus.emit(DeliveryEvent(
        event_type=EventType.STATION_READY,
        delivery_id=delivery_id,
        language=language,
        details=details,
    ))
