import json
import re

from ..models import ResearchTask, SearchSource, TaskFact, TaskSummary
from ..prompts import SUMMARIZER_SYSTEM
from .llm import chat


def extract_object(text: str) -> dict:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("任务总结结果中没有找到 JSON 对象")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("任务总结结果不是对象")
    return value


async def summarize(task: ResearchTask, sources: list[SearchSource]) -> TaskSummary:
    source_text = "\n\n".join(f"[{source.id}] {source.title}\nURL: {source.url}\n摘要: {source.content}" for source in sources)
    text = await chat([{"role": "system", "content": SUMMARIZER_SYSTEM}, {"role": "user", "content": f"任务标题：{task.title}\n任务意图：{task.intent}\n搜索查询：{task.query}\n\n来源资料：\n{source_text}"}], "summarizing")
    data = extract_object(text)
    allowed = {source.id for source in sources}
    facts = [TaskFact(claim=str(item.get("claim", "")), source_ids=[source_id for source_id in item.get("source_ids", []) if source_id in allowed], confidence=float(item.get("confidence", 0))) for item in data.get("facts", []) if isinstance(item, dict)]
    source_ids = sorted({source_id for fact in facts for source_id in fact.source_ids})
    return TaskSummary(task_id=task.id, summary=str(data.get("summary", "")), facts=facts, source_ids=source_ids, open_questions=[str(item) for item in data.get("open_questions", [])])
