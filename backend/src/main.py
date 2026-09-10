import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import APITimeoutError, AsyncOpenAI

load_dotenv()
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("deep-research")


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip("'").strip('"')


def missing_settings() -> list[str]:
    return [name for name in ["TAVILY_API_KEY", "LLM_API_KEY", "LLM_MODEL_ID", "LLM_BASE_URL"] if not setting(name)]


def event(status: str, progress: int, message: str, topic: str, report: str | None = None) -> str:
    data: dict[str, Any] = {"status": status, "progress": progress, "message": message, "topic": topic}
    if report is not None:
        data["report"] = report
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def llm_chat(messages: list[dict[str, str]], phase: str) -> str:
    base_url = setting("LLM_BASE_URL").rstrip("/")
    timeout = float(setting("LLM_PLAN_TIMEOUT" if phase == "planning" else "LLM_REPORT_TIMEOUT", setting("LLM_TIMEOUT", "120")))
    max_tokens = int(setting("LLM_PLAN_MAX_TOKENS" if phase == "planning" else "LLM_REPORT_MAX_TOKENS", setting("LLM_MAX_TOKENS", "2500")))
    retries = int(setting("UPSTREAM_RETRIES", "2"))
    url = f"{base_url}/chat/completions"
    started = time.perf_counter()
    logger.info("LLM started phase=%s model=%s url=%s timeout=%ss max_tokens=%s", phase, setting("LLM_MODEL_ID"), url, timeout, max_tokens)
    for attempt in range(retries + 1):
        client = AsyncOpenAI(api_key=setting("LLM_API_KEY"), base_url=base_url, timeout=timeout, max_retries=0)
        try:
            response = await asyncio.wait_for(client.chat.completions.create(model=setting("LLM_MODEL_ID"), messages=messages, temperature=float(setting("LLM_TEMPERATURE", "0.2")), max_tokens=max_tokens), timeout=timeout + 5)
            content = response.choices[0].message.content or ""
            logger.info("LLM completed phase=%s chars=%s elapsed=%.2fs attempt=%s", phase, len(content), time.perf_counter() - started, attempt + 1)
            return content
        except (APITimeoutError, TimeoutError, asyncio.TimeoutError) as exc:
            logger.warning("LLM timeout phase=%s attempt=%s/%s", phase, attempt + 1, retries + 1)
            if attempt >= retries:
                raise TimeoutError(f"LLM {phase} 阶段超时（单次 {timeout:g} 秒，重试 {retries} 次）") from exc
        except Exception as exc:
            logger.exception("LLM failed phase=%s error_type=%s error=%s", phase, type(exc).__name__, exc)
            raise
        finally:
            await client.close()
        await asyncio.sleep(min(2**attempt, 8))
    raise RuntimeError("LLM 未返回结果")


async def tavily_search(query: str) -> list[dict[str, Any]]:
    url = f"{setting('TAVILY_BASE_URL', 'https://api.tavily.com').rstrip('/')}/search"
    payload = {"api_key": setting("TAVILY_API_KEY"), "query": query, "search_depth": setting("SEARCH_TOPIC_DEPTH", "advanced"), "max_results": int(setting("TAVILY_MAX_RESULTS", "5")), "include_answer": False, "include_raw_content": False}
    timeout = float(setting("TAVILY_TIMEOUT", setting("LLM_TIMEOUT", "60")))
    retries = int(setting("UPSTREAM_RETRIES", "2"))
    for attempt in range(retries + 1):
        try:
            logger.info("Tavily started query=%r timeout=%ss attempt=%s", query, timeout, attempt + 1)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                if response.is_error:
                    logger.error("Tavily error status=%s body=%s", response.status_code, response.text[:500])
                response.raise_for_status()
                results = response.json().get("results", [])
            logger.info("Tavily completed results=%s", len(results))
            return results
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("Tavily transient failure type=%s attempt=%s/%s", type(exc).__name__, attempt + 1, retries + 1)
            if attempt >= retries:
                raise TimeoutError(f"Tavily 搜索超时（单次 {timeout:g} 秒，重试 {retries} 次）") from exc
            await asyncio.sleep(min(2**attempt, 8))
    raise RuntimeError("Tavily 未返回结果")


async def with_heartbeat(awaitable, topic: str, phase: str, progress: int) -> AsyncGenerator[Any, None]:
    task = asyncio.create_task(awaitable)
    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=15)
        except asyncio.TimeoutError:
            yield event(phase, progress, "上游服务仍在处理中，请稍候...", topic)
    yield task.result()


async def research_events(topic: str) -> AsyncGenerator[str, None]:
    started = time.perf_counter()
    logger.info("Research started topic=%r", topic)
    try:
        missing = missing_settings()
        if missing:
            raise RuntimeError(f"请在 backend/.env 中配置：{', '.join(missing)}")
        yield event("planning", 5, "正在调用大模型制定研究计划...", topic)
        plan_text = None
        plan_messages = [{"role": "system", "content": "你是研究规划专家。只返回 JSON 数组，每项包含 title、intent、query，最多 4 项。"}, {"role": "user", "content": f"为以下主题制定互不重复、覆盖全面的检索计划：{topic}"}]
        async for result in with_heartbeat(llm_chat(plan_messages, "planning"), topic, "planning", 5):
            if isinstance(result, str) and result.startswith("data: "):
                yield result
            else:
                plan_text = result
        try:
            plan = json.loads(plan_text or "")
            if not isinstance(plan, list):
                raise ValueError("结果不是数组")
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"模型规划结果不是有效 JSON：{exc}") from exc
        plan = plan[:int(setting("MAX_RESEARCH_TASKS", "4"))]
        yield event("planning", 20, f"已生成 {len(plan)} 个研究方向", topic)
        findings: list[str] = []
        sources: list[dict[str, str]] = []
        for index, task in enumerate(plan):
            title, query = str(task.get("title", topic)), str(task.get("query", topic))
            results = None
            async for result in with_heartbeat(tavily_search(query), topic, "searching", 25 + index * 10):
                if isinstance(result, str) and result.startswith("data: "):
                    yield result
                else:
                    results = result
            compact = [{"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", "")[:1500]} for item in (results or [])]
            sources.extend({"title": item["title"], "url": item["url"]} for item in compact if item["url"])
            findings.append(f"### {title}\n研究意图：{task.get('intent', '')}\n资料：{json.dumps(compact, ensure_ascii=False)}")
            yield event("searching", 25 + int((index + 1) / max(len(plan), 1) * 45), f"已完成：{title}", topic)
        yield event("synthesizing", 80, "正在调用大模型生成研究报告...", topic)
        findings_text = "\n\n".join(findings)
        report_messages = [{"role": "system", "content": "你是严谨的研究报告作者。使用中文 Markdown，区分事实与推断，不要编造资料。引用来源时使用 [来源序号]。"}, {"role": "user", "content": f"主题：{topic}\n\n检索资料：\n{findings_text}\n\n来源：{json.dumps(sources, ensure_ascii=False)}\n\n请生成包含摘要、关键发现、分析、局限性和参考来源的报告。"}]
        report = None
        async for result in with_heartbeat(llm_chat(report_messages, "report"), topic, "synthesizing", 80):
            if isinstance(result, str) and result.startswith("data: "):
                yield result
            else:
                report = result
        yield event("completed", 100, "研究完成", topic, report or "")
        logger.info("Research completed topic=%r elapsed=%.2fs sources=%s", topic, time.perf_counter() - started, len(sources))
    except Exception as exc:
        message = str(exc).strip() or f"{type(exc).__name__}: 上游服务未返回详细错误"
        logger.exception("Research failed topic=%r error=%s elapsed=%.2fs", topic, message, time.perf_counter() - started)
        yield event("error", 0, message, topic)


app = FastAPI(title="Deep Research Agent API", version="0.3.0")
origins = [item.strip() for item in setting("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict[str, Any]:
    missing = missing_settings()
    logger.info("Health check status=%s missing=%s", "ok" if not missing else "misconfigured", missing)
    return {"status": "ok" if not missing else "misconfigured", "service": "deep-research-agent", "missing": missing}


@app.get("/api/research/stream")
async def stream_research(topic: str) -> StreamingResponse:
    logger.info("SSE requested topic=%r", topic)
    if len(topic.strip()) < 2:
        return StreamingResponse(iter([event("error", 0, "研究主题至少需要 2 个字符", topic)]), media_type="text/event-stream")
    return StreamingResponse(research_events(topic.strip()), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@app.get("/api/time")
async def current_time() -> dict[str, str]:
    return {"utc": datetime.now(timezone.utc).isoformat()}
