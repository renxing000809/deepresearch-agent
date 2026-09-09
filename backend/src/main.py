import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("deep-research")
log_file = os.getenv("LOG_FILE", "").strip()
if log_file:
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(file_handler)


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=500)


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip("'").strip('"')


def missing_settings() -> list[str]:
    names = ["TAVILY_API_KEY", "LLM_API_KEY", "LLM_MODEL_ID", "LLM_BASE_URL"]
    return [name for name in names if not setting(name)]


async def llm_chat(messages: list[dict[str, str]]) -> str:
    url = f"{setting('LLM_BASE_URL').rstrip('/')}"
    started = time.perf_counter()
    logger.info("LLM request started: model=%s url=%s messages=%d", setting("LLM_MODEL_ID"), url, len(messages))
    try:
        client = AsyncOpenAI(
            api_key=setting("LLM_API_KEY"),
            base_url=setting("LLM_BASE_URL").rstrip("/"),
            timeout=float(setting("LLM_TIMEOUT", "60")),
            max_retries=0,
        )
        try:
            response = await client.chat.completions.create(
                model=setting("LLM_MODEL_ID"),
                messages=messages,
                temperature=float(setting("LLM_TEMPERATURE", "0.2")),
                max_tokens=int(setting("LLM_MAX_TOKENS", "4000")),
            )
        finally:
            await client.close()
        content = response.choices[0].message.content or ""
        logger.info("LLM request completed: output_chars=%d", len(content))
        return content
    except Exception as exc:
        logger.exception("LLM request failed: error_type=%s error=%s url=%s elapsed=%.2fs", type(exc).__name__, str(exc), url, time.perf_counter() - started)
        raise


async def tavily_search(query: str) -> list[dict[str, Any]]:
    url = f"{setting('TAVILY_BASE_URL', 'https://api.tavily.com').rstrip('/')}/search"
    payload = {
        "api_key": setting("TAVILY_API_KEY"),
        "query": query,
        "search_depth": setting("SEARCH_TOPIC_DEPTH", "advanced"),
        "max_results": int(setting("TAVILY_MAX_RESULTS", "5")),
        "include_answer": False,
        "include_raw_content": False,
    }
    started = time.perf_counter()
    logger.info("Tavily request started: query=%r depth=%s max_results=%s", query, payload["search_depth"], payload["max_results"])
    try:
        async with httpx.AsyncClient(timeout=float(setting("LLM_TIMEOUT", "60"))) as client:
            response = await client.post(url, json=payload)
            logger.info("Tavily response: status=%s elapsed=%.2fs", response.status_code, time.perf_counter() - started)
            if response.is_error:
                logger.error("Tavily error body: %s", response.text[:1000])
            response.raise_for_status()
            results = response.json().get("results", [])
        logger.info("Tavily request completed: results=%d", len(results))
        return results
    except Exception:
        logger.exception("Tavily request failed: url=%s query=%r elapsed=%.2fs", url, query, time.perf_counter() - started)
        raise


app = FastAPI(title="Deep Research Agent API", version="0.2.0")
origins = [item.strip() for item in setting("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict[str, Any]:
    missing = missing_settings()
    logger.info("Health check: status=%s missing=%s", "ok" if not missing else "misconfigured", missing)
    return {"status": "ok" if not missing else "misconfigured", "service": "deep-research-agent", "missing": missing}


def event(status: str, progress: int, message: str, topic: str, report: str | None = None) -> str:
    payload: dict[str, Any] = {"status": status, "progress": progress, "message": message, "topic": topic}
    if report is not None:
        payload["report"] = report
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def research_events(topic: str) -> AsyncGenerator[str, None]:
    request_started = time.perf_counter()
    logger.info("Research started: topic=%r", topic)
    try:
        missing = missing_settings()
        if missing:
            logger.error("Research blocked by missing settings: %s", missing)
            raise RuntimeError(f"请在 backend/.env 中配置：{', '.join(missing)}")

        yield event("planning", 5, "正在调用大模型制定研究计划...", topic)
        plan_text = await llm_chat([
            {"role": "system", "content": "你是研究规划专家。只返回 JSON 数组，每项包含 title、intent、query，最多 4 项。"},
            {"role": "user", "content": f"为以下主题制定互不重复、覆盖全面的检索计划：{topic}"},
        ])
        try:
            plan = json.loads(plan_text)
            if not isinstance(plan, list):
                raise ValueError("结果不是数组")
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"模型规划结果不是有效 JSON：{exc}") from exc
        plan = plan[: int(setting("MAX_RESEARCH_TASKS", "4"))]
        logger.info("Research plan created: tasks=%d", len(plan))
        yield event("planning", 20, f"已生成 {len(plan)} 个研究方向", topic)

        findings: list[str] = []
        sources: list[dict[str, str]] = []
        for index, task in enumerate(plan):
            title = str(task.get("title", task.get("query", topic)))
            query = str(task.get("query", topic))
            results = await tavily_search(query)
            compact = [{"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", "")[:3000]} for item in results]
            sources.extend({"title": item["title"], "url": item["url"]} for item in compact if item["url"])
            findings.append(f"### {title}\n研究意图：{task.get('intent', '')}\n资料：{json.dumps(compact, ensure_ascii=False)}")
            progress = 25 + int((index + 1) / max(len(plan), 1) * 45)
            yield event("searching", progress, f"已完成：{title}", topic)

        yield event("synthesizing", 80, "正在调用大模型生成带来源的研究报告...", topic)
        findings_text = "\n\n".join(findings)
        report = await llm_chat([
            {"role": "system", "content": "你是严谨的研究报告作者。使用中文 Markdown，区分事实与推断，不要编造资料。引用来源时使用 [来源序号]。"},
            {"role": "user", "content": f"主题：{topic}\n\n检索资料：\n{findings_text}\n\n来源：{json.dumps(sources, ensure_ascii=False)}\n\n请生成包含摘要、关键发现、分析、局限性和参考来源的报告。"},
        ])
        yield event("completed", 100, "研究完成", topic, report)
        logger.info("Research completed: topic=%r elapsed=%.2fs sources=%d", topic, time.perf_counter() - request_started, len(sources))
    except Exception as exc:
        error_message = str(exc).strip() or f"{type(exc).__name__}: 上游服务未返回详细错误"
        logger.exception("Research failed: topic=%r error=%s elapsed=%.2fs", topic, error_message, time.perf_counter() - request_started)
        yield event("error", 0, error_message, topic)


@app.get("/api/research/stream")
async def stream_research(topic: str) -> StreamingResponse:
    logger.info("SSE connection requested: topic=%r", topic)
    if len(topic.strip()) < 2:
        logger.warning("SSE request rejected: topic is too short")
        return StreamingResponse(iter([event("error", 0, "研究主题至少需要 2 个字符", topic)]), media_type="text/event-stream")
    return StreamingResponse(research_events(topic.strip()), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@app.get("/api/time")
async def current_time() -> dict[str, str]:
    return {"utc": datetime.now(timezone.utc).isoformat()}
