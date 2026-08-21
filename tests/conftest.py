"""Pytest configuration and shared fixtures for Passline tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from passline.events.bus import EventBus

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_srt_bytes() -> bytes:
    """LF-only SRT fixture with no BOM."""
    return (FIXTURES_DIR / "sample.srt").read_bytes()


@pytest.fixture
def sample_crlf_bytes() -> bytes:
    """CRLF SRT fixture with no BOM."""
    return (FIXTURES_DIR / "sample_crlf.srt").read_bytes()


@pytest.fixture
def sample_bom_bytes() -> bytes:
    """LF SRT fixture with UTF-8 BOM."""
    return (FIXTURES_DIR / "sample_bom.srt").read_bytes()


@pytest.fixture
def tmp_event_log(tmp_path: Path) -> EventBus:
    """An EventBus backed by a temporary log file that is discarded after the test."""
    return EventBus(tmp_path / "events.jsonl")
