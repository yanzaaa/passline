"""Pytest configuration and shared fixtures for Passline tests.

Registers custom markers and CLI options:

  --live-llm     Opt-in to tests that make real LLM API calls (network required,
                 GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT must be set).

Tests decorated with ``@pytest.mark.live_llm`` are skipped automatically unless
``--live-llm`` is passed on the command line.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from unittest.mock import patch

from passline.events.bus import EventBus

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ── Global Mocks ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mock_genai_client(request: pytest.FixtureRequest):
    """Ensure no real google.genai.Client is instantiated during hermetic tests.

    If a test is marked with @pytest.mark.live_llm, the real client is allowed.
    """
    if request.node.get_closest_marker("live_llm"):
        yield
        return
    with patch("google.genai.Client") as mock:
        yield mock


# ── Standard SRT fixtures ────────────────────────────────────────────────────

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


# ── Live LLM CLI option & marker ─────────────────────────────────────────────

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-llm",
        action="store_true",
        default=False,
        help="Run tests that make real LLM API calls (requires credentials).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_llm: mark test as requiring a live LLM API call (skipped by default).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--live-llm"):
        return  # run everything
    skip_live = pytest.mark.skip(reason="requires --live-llm flag and API credentials")
    for item in items:
        if item.get_closest_marker("live_llm"):
            item.add_marker(skip_live)
