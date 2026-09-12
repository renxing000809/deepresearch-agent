import json
import re

from ..models import ResearchTask
from ..prompts import PLANNER_SYSTEM
from .llm import chat


def extract_json(text: str) -> object:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise ValueError("模型规划结果中没有找到 JSON 数组")
    return json.loads(match.group(0))


async def plan(topic: str) -> list[ResearchTask]:
    text = await chat([{"role": "system", "content": PLANNER_SYSTEM}, {"role": "user", "content": f"研究主题：{topic}"}], "planning")
    payload = extract_json(text)
    if not isinstance(payload, list):
        raise ValueError("模型规划结果不是数组")
    tasks: list[ResearchTask] = []
    for index, item in enumerate(payload[:int(__import__("os").getenv("MAX_RESEARCH_TASKS", "4"))], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个研究任务不是对象")
        tasks.append(ResearchTask(id=f"task-{index:03d}", title=str(item.get("title", "")).strip(), intent=str(item.get("intent", "")).strip(), query=str(item.get("query", "")).strip()))
    if not tasks:
        raise ValueError("模型没有生成有效研究任务")
    return tasks
