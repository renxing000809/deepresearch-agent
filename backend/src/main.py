import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .models import ResearchEvent, SearchSource, TaskSummary
from .services import planner, reporter, search, summarizer

load_dotenv()
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("deep-research")


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip("'").strip('"')


def missing_settings() -> list[str]:
    return [name for name in ["TAVILY_API_KEY", "LLM_API_KEY", "LLM_MODEL_ID", "LLM_BASE_URL"] if not setting(name)]


def event(topic: str, event_type: str, status: str, progress: int, message: str, task_id: str | None = None, report: str | None = None, data: dict[str, Any] | None = None) -> str:
    payload = ResearchEvent(type=event_type, status=status, progress=progress, message=message, topic=topic, task_id=task_id, report=report, data=data or {})
    return f"data: {payload.model_dump_json(exclude_none=True)}\n\n"


def is_sse_event(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("data: ")


async def with_heartbeat(awaitable, topic: str, phase: str, progress: int) -> AsyncGenerator[Any, None]:
    task = asyncio.create_task(awaitable)
    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=15)
        except asyncio.TimeoutError:
            yield event(topic, "heartbeat", phase, progress, "上游服务仍在处理中，请稍候...")
    yield task.result()


def assign_source_ids(sources: list[SearchSource], next_id: int) -> int:
    for source in sources:
        source.id = f"S{next_id:03d}"
        next_id += 1
    return next_id


async def research_events(topic: str) -> AsyncGenerator[str, None]:
    started = datetime.now(timezone.utc)
    logger.info("Research started topic=%r", topic)
    try:
        missing = missing_settings()
        if missing:
            raise RuntimeError(f"请在 backend/.env 中配置：{', '.join(missing)}")

        yield event(topic, "research_started", "planning", 1, "研究已开始")
        tasks = None
        async for result in with_heartbeat(planner.plan(topic), topic, "planning", 5):
            if is_sse_event(result):
                yield result
            else:
                tasks = result
        if tasks is None:
            raise RuntimeError("规划阶段没有返回任务")
        yield event(topic, "plan_created", "planning", 15, f"已生成 {len(tasks)} 个研究方向", data={"tasks": [task.model_dump() for task in tasks]})

        all_sources: list[SearchSource] = []
        summaries: list[TaskSummary] = []
        next_source_id = 1
        for index, task in enumerate(tasks):
            task.status = "searching"
            progress = 20 + int(index / max(len(tasks), 1) * 60)
            yield event(topic, "task_started", "searching", progress, f"开始研究：{task.title}", task.id, data={"task": task.model_dump()})
            sources = None
            yield event(topic, "search_started", "searching", progress, f"正在搜索：{task.title}", task.id)
            async for result in with_heartbeat(search.search(task.query, task.id), topic, "searching", progress):
                if is_sse_event(result):
                    yield result
                else:
                    sources = result
            task_sources = sources or []
            next_source_id = assign_source_ids(task_sources, next_source_id)
            all_sources.extend(task_sources)
            yield event(topic, "search_completed", "filtering", progress + 2, f"搜索完成：{len(task_sources)} 个来源", task.id, data={"source_count": len(task_sources), "sources": [source.model_dump() for source in task_sources]})

            task.status = "summarizing"
            yield event(topic, "summary_started", "summarizing", progress + 4, f"正在总结：{task.title}", task.id)
            summary = None
            async for result in with_heartbeat(summarizer.summarize(task, task_sources), topic, "summarizing", progress + 4):
                if is_sse_event(result):
                    yield result
                else:
                    summary = result
            if summary is None:
                raise RuntimeError(f"任务 {task.title} 没有生成摘要")
            summaries.append(summary)
            task.status = "completed"
            yield event(topic, "summary_completed", "summarizing", progress + 6, f"任务摘要完成：{task.title}", task.id, data={"summary": summary.model_dump()})
            yield event(topic, "task_completed", "searching", progress + 8, f"任务完成：{task.title}", task.id, data={"source_count": len(task_sources)})

        yield event(topic, "report_started", "reporting", 85, "正在基于任务摘要生成最终报告")
        final_report = None
        async for result in with_heartbeat(reporter.report(topic, summaries, all_sources), topic, "reporting", 85):
            if is_sse_event(result):
                yield result
            else:
                final_report = result
        yield event(topic, "report_completed", "completed", 100, "研究完成", report=final_report or "", data={"source_count": len(all_sources), "summary_count": len(summaries)})
        logger.info("Research completed topic=%r elapsed=%.2fs sources=%s summaries=%s", topic, (datetime.now(timezone.utc) - started).total_seconds(), len(all_sources), len(summaries))
    except Exception as exc:
        logger.exception("Research failed topic=%r error=%s", topic, exc)
        yield event(topic, "research_failed", "error", 0, str(exc) or f"{type(exc).__name__}: 上游服务未返回详细错误")


app = FastAPI(title="Deep Research Agent API", version="0.4.0")
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
        return StreamingResponse(iter([event(topic, "research_failed", "error", 0, "研究主题至少需要 2 个字符")]), media_type="text/event-stream")
    return StreamingResponse(research_events(topic.strip()), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@app.get("/api/time")
async def current_time() -> dict[str, str]:
    return {"utc": datetime.now(timezone.utc).isoformat()}
