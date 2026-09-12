import re

from ..models import SearchSource, TaskSummary
from ..prompts import REPORTER_SYSTEM
from .llm import chat


async def report(topic: str, summaries: list[TaskSummary], sources: list[SearchSource]) -> str:
    summary_text = "\n\n".join(f"## {item.task_id}\n{item.summary}\n关键事实：{[(fact.claim, fact.source_ids) for fact in item.facts]}" for item in summaries)
    source_text = "\n".join(f"[{source.id}] {source.title} - {source.url}" for source in sources)
    result = await chat([{"role": "system", "content": REPORTER_SYSTEM}, {"role": "user", "content": f"研究主题：{topic}\n\n任务摘要：\n{summary_text}\n\n来源注册表：\n{source_text}"}], "report")
    valid_ids = {source.id for source in sources}
    cited_ids = set(re.findall(r"\[(S\d+)\]", result))
    invalid = cited_ids - valid_ids
    if invalid:
        result += f"\n\n> 引用校验提示：发现未注册来源 {', '.join(sorted(invalid))}。"
    return result
