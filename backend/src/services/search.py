import asyncio
import logging
import os
import time
from typing import Any

import httpx

from ..models import SearchSource

logger = logging.getLogger("deep-research.search")


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip("'").strip('"')


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


async def search(query: str, task_id: str) -> list[SearchSource]:
    url = f"{setting('TAVILY_BASE_URL', 'https://api.tavily.com').rstrip('/')}/search"
    timeout = float(setting("TAVILY_TIMEOUT", setting("LLM_TIMEOUT", "60")))
    retries = int(setting("UPSTREAM_RETRIES", "2"))
    payload = {"api_key": setting("TAVILY_API_KEY"), "query": query, "search_depth": setting("SEARCH_TOPIC_DEPTH", "advanced"), "max_results": int(setting("TAVILY_MAX_RESULTS", "5")), "include_answer": False, "include_raw_content": False}
    started = time.perf_counter()

    for attempt in range(retries + 1):
        try:
            logger.info("Tavily started task=%s query=%r attempt=%s", task_id, query, attempt + 1)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                if response.is_error:
                    logger.error("Tavily error status=%s body=%s", response.status_code, response.text[:500])
                response.raise_for_status()
                raw_results = response.json().get("results", [])

            sources: list[SearchSource] = []
            seen: set[str] = set()
            for item in raw_results:
                normalized = normalize_url(str(item.get("url", "")))
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                sources.append(SearchSource(id="", task_id=task_id, title=str(item.get("title", "")), url=normalized, content=str(item.get("content", ""))[:1500]))
            logger.info("Tavily completed task=%s results=%s unique=%s elapsed=%.2fs", task_id, len(raw_results), len(sources), time.perf_counter() - started)
            return sources
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("Tavily transient failure task=%s type=%s attempt=%s/%s", task_id, type(exc).__name__, attempt + 1, retries + 1)
            if attempt >= retries:
                raise TimeoutError(f"Tavily 搜索超时（单次 {timeout:g} 秒，重试 {retries} 次）") from exc
            await asyncio.sleep(min(2**attempt, 8))
    raise RuntimeError("Tavily 未返回结果")
