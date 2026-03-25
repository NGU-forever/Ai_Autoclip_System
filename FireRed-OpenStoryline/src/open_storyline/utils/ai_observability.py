from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import httpx


DEFAULT_TIMEOUT_SECONDS = 2.0
ENV_ENDPOINT = "OPENSTORYLINE_OBSERVABILITY_ENDPOINT"
ENV_API_KEY = "OPENSTORYLINE_OBSERVABILITY_API_KEY"


def _endpoint() -> str:
    return (os.getenv(ENV_ENDPOINT) or "").strip()


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (os.getenv(ENV_API_KEY) or "").strip()
    if key:
        headers["X-Api-Key"] = key
    return headers


async def report_ai_call(
    *,
    provider: str,
    source: str,
    success: bool,
    latency_ms: int,
    model: Optional[str] = None,
    error_message: Optional[str] = None,
    prompt_chars: int = 0,
    response_chars: int = 0,
    request_id: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    endpoint = _endpoint()
    if not endpoint:
        return

    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "success": bool(success),
        "error_message": error_message,
        "latency_ms": max(0, int(latency_ms)),
        "prompt_chars": max(0, int(prompt_chars)),
        "response_chars": max(0, int(response_chars)),
        "source": source,
        "request_id": request_id,
        "meta": meta or {},
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            await client.post(endpoint, json=payload, headers=_headers())
    except Exception:
        # Telemetry is best-effort only; never impact editing flow.
        return


def queue_ai_call_report(**kwargs: Any) -> None:
    """
    Fire-and-forget wrapper that safely schedules reporting.
    Must not raise in request/tool paths.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(report_ai_call(**kwargs))
