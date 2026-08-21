"""Rate-limit-aware Semantic Scholar Graph API client."""

from __future__ import annotations

import asyncio
import time

import httpx

from config import cfg


_request_lock = asyncio.Lock()
_next_request_at = 0.0


def _headers() -> dict[str, str]:
    api_key = cfg.semantic_scholar.get("api_key")
    return {"x-api-key": api_key} if api_key else {}


async def get_json(path: str, params: dict, max_attempts: int = 4) -> dict:
    """Issue a throttled GET and retry 429 responses with bounded backoff."""
    global _next_request_at

    settings = cfg.semantic_scholar
    url = f"{settings.base_url.rstrip('/')}/{path.lstrip('/')}"
    last_response: httpx.Response | None = None

    for attempt in range(max_attempts):
        async with _request_lock:
            delay = _next_request_at - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

            async with httpx.AsyncClient(
                timeout=settings.timeout,
                headers=_headers(),
            ) as client:
                response = await client.get(url, params=params)

            # Semantic Scholar API keys are commonly provisioned at 1 request/s.
            # A shared schedule prevents concurrent search/detail/graph requests
            # from immediately exhausting that allowance.
            _next_request_at = time.monotonic() + 1.05

        last_response = response
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()

        retry_after = response.headers.get("Retry-After")
        try:
            backoff = float(retry_after) if retry_after else 2 ** attempt
        except ValueError:
            backoff = 2 ** attempt
        await asyncio.sleep(min(max(backoff, 1.0), 8.0))

    assert last_response is not None
    last_response.raise_for_status()
    return {}
