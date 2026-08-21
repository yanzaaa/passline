"""Shared ADK agent callbacks for Passline.

Provides an exponential-backoff retry factory that wraps the Gemini model's
``generate_content_async`` method with tenacity so rate-limit errors (HTTP 429
/ quota exceeded) trigger automatic back-off and retry.

Usage::

    from passline.agents.callbacks import install_retry_on_model
    from google.adk import Agent

    agent = Agent(name="my_agent", model="gemini-3-flash-preview", ...)
    install_retry_on_model(agent, max_attempts=4, base_delay_s=1.0)

``install_retry_on_model`` must be called AFTER the agent is constructed
because ADK resolves the model instance lazily.  Call it once per agent
instance; it is idempotent.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, AsyncGenerator

from google.genai.errors import ClientError

log = logging.getLogger(__name__)

# Marker attribute set on the model to prevent double-wrapping
_RETRY_INSTALLED = "_passline_retry_installed"

# HTTP status code for rate limiting / quota exceeded
_RATE_LIMIT_CODE = 429


def _is_rate_limit(exc: Exception) -> bool:
    """Return True when *exc* is a 429 / quota-exceeded response."""
    if isinstance(exc, ClientError):
        return exc.code == _RATE_LIMIT_CODE
    # google.api_core.exceptions.ResourceExhausted (if present transitively)
    cls_name = type(exc).__name__
    return cls_name in ("ResourceExhausted", "TooManyRequests")


def install_retry_on_model(
    agent: Any,
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
) -> None:
    """Patch *agent*'s resolved model with exponential-backoff retry.

    The patch wraps ``model.generate_content_async`` so that any rate-limit
    exception triggers a wait then retry (up to *max_attempts* total tries).

    Parameters
    ----------
    agent:
        An ADK ``LlmAgent`` instance whose ``canonical_model`` attribute
        holds the resolved model object.
    max_attempts:
        Total number of attempts (1 = no retry).
    base_delay_s:
        Base delay in seconds; actual delay is
        ``base_delay_s * 2^attempt + uniform(0, 0.5)``.
    """
    # ADK resolves the model via canonical_model property
    model = getattr(agent, "canonical_model", None)
    if model is None:
        log.warning(
            "install_retry_on_model: agent %s has no canonical_model — skipping",
            getattr(agent, "name", repr(agent)),
        )
        return

    if getattr(model, _RETRY_INSTALLED, False):
        return  # Already patched

    original = model.generate_content_async

    async def _with_retry(
        llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[Any, None]:
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                async for chunk in original(llm_request, stream=stream):
                    yield chunk
                return  # success — exit retry loop
            except Exception as exc:
                last_exc = exc
                if not _is_rate_limit(exc):
                    raise  # non-rate-limit error — propagate immediately
                if attempt + 1 >= max_attempts:
                    break  # exhausted — let the final raise happen below
                delay = base_delay_s * (2 ** attempt) + random.uniform(0, 0.5)
                log.warning(
                    "Rate limit on attempt %d/%d for model %s — "
                    "retrying in %.1fs",
                    attempt + 1,
                    max_attempts,
                    getattr(model, "model_name", "?"),
                    delay,
                )
                await asyncio.sleep(delay)

        # All attempts exhausted — re-raise the last exception
        assert last_exc is not None
        raise last_exc

    object.__setattr__(model, "generate_content_async", _with_retry)
    object.__setattr__(model, _RETRY_INSTALLED, True)
    log.debug(
        "install_retry_on_model: patched model %s on agent %s "
        "(max_attempts=%d, base_delay=%.1fs)",
        getattr(model, "model_name", repr(model)),
        getattr(agent, "name", repr(agent)),
        max_attempts,
        base_delay_s,
    )
