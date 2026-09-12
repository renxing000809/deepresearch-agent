import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models import ResearchTask, SearchSource, TaskSummary
from src import main
from src.services.planner import extract_json
from src.services.summarizer import extract_object
from src.services import reporter


class PipelineTest(unittest.TestCase):
    def test_extract_planner_json_from_code_block(self):
        result = extract_json('```json\n[{"title":"基础信息","intent":"了解基础","query":"topic overview"}]\n```')
        self.assertEqual(result[0]["query"], "topic overview")

    def test_extract_summary_json(self):
        result = extract_object('{"summary":"摘要","facts":[],"open_questions":[]}')
        self.assertEqual(result["summary"], "摘要")

    def test_reporter_flags_unknown_source(self):
        async def run():
            task = ResearchTask(id="task-001", title="测试", intent="验证", query="test")
            source = SearchSource(id="S001", task_id=task.id, title="来源", url="https://example.com", content="内容")
            with patch.object(reporter, "chat", new=AsyncMock(return_value="结论 [S999]")):
                return await reporter.report("测试主题", [], [source])

        result = asyncio.run(run())
        self.assertIn("S999", result)
        self.assertIn("引用校验提示", result)

    def test_research_pipeline_emits_task_summary_events(self):
        async def run():
            task = ResearchTask(id="task-001", title="测试任务", intent="验证流程", query="test")
            source = SearchSource(id="", task_id=task.id, title="来源", url="https://example.com", content="内容")
            summary = TaskSummary(task_id=task.id, summary="任务摘要", source_ids=["S001"])
            with patch.object(main, "missing_settings", return_value=[]), \
                patch.object(main.planner, "plan", new=AsyncMock(return_value=[task])), \
                patch.object(main.search, "search", new=AsyncMock(return_value=[source])), \
                patch.object(main.summarizer, "summarize", new=AsyncMock(return_value=summary)), \
                patch.object(main.reporter, "report", new=AsyncMock(return_value="# 报告 [S001]")):
                return [json.loads(item.removeprefix("data: ").strip()) async for item in main.research_events("测试主题")]

        events = asyncio.run(run())
        event_types = [item["type"] for item in events]
        self.assertIn("summary_started", event_types)
        self.assertIn("summary_completed", event_types)
        self.assertEqual(events[-1]["status"], "completed")
        self.assertEqual(events[-1]["report"], "# 报告 [S001]")


if __name__ == "__main__":
    unittest.main()
