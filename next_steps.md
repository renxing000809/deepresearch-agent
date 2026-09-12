# DeepResearch 下一步实施计划

本文档用于记录当前项目后续优化事项，避免后续开发遗漏设计目标。执行任务时应按照优先级从上到下推进，并在完成后更新任务状态和验收结果。

## 1. 当前状态

当前系统已经跑通基础闭环：

```text
Vue 3
  -> FastAPI SSE
  -> Tokeness LLM 生成研究计划
  -> Tavily 搜索
  -> Tokeness LLM 生成最终报告
  -> 前端展示
```

当前定位：

```text
LLM 驱动的线性研究流水线
```

目标定位：

```text
具备任务级总结、状态机、上下文缓存、搜索降级、网页质量过滤、反思循环和长期记忆的生产级 Deep Research Agent
```

详细 Gap 和目标架构见：

```text
gap.md
```

## 2. 当前开发阶段

当前应优先完成 Phase 1：

```text
稳定当前链路 + 任务级摘要 + 结构化数据模型 + 任务级 SSE
```

不要在 Phase 1 尚未完成前优先实现长期记忆、复杂多智能体自由对话或大规模并发。

## 3. P0：立即执行

### 3.1 实现任务级 SummarizerAgent

目标：避免将所有 Tavily 原始结果直接拼接到最终报告 Prompt 中。

当前流程：

```text
规划
  -> Tavily 搜索多个任务
  -> 所有原始结果汇总
  -> 最终报告 LLM
```

目标流程：

```text
规划
  -> 任务 1 搜索
  -> 任务 1 总结
  -> 任务 2 搜索
  -> 任务 2 总结
  -> 最终报告只读取任务摘要
```

新增职责：

- 接收一个 `ResearchTask`
- 接收经过过滤的搜索来源
- 提取核心事实
- 保留来源引用
- 输出任务级 Markdown 或结构化摘要
- 输出未解决问题
- 输出事实置信度

建议输出：

```json
{
  "task_id": "task-001",
  "summary": "...",
  "facts": [
    {
      "claim": "...",
      "source_ids": ["S001", "S002"],
      "confidence": 0.86
    }
  ],
  "open_questions": [],
  "source_ids": ["S001", "S002"]
}
```

验收标准：

- 每个研究任务独立调用一次总结逻辑。
- 最终报告不再直接读取全部原始网页内容。
- 单个任务摘要失败时能明确标记任务失败。
- 报告阶段输入内容明显小于当前实现。
- 规划、任务总结和报告生成分别记录耗时和 Token 使用量。

### 3.2 增加结构化数据模型

新增：

```text
backend/src/models.py
```

至少定义：

```python
ResearchTask
SearchSource
TaskSummary
ResearchState
ResearchEvent
```

建议字段：

```python
class ResearchTask(BaseModel):
    id: str
    title: str
    intent: str
    query: str
    status: str = "pending"


class SearchSource(BaseModel):
    id: str
    title: str
    url: str
    content: str
    quality_score: float | None = None


class TaskSummary(BaseModel):
    task_id: str
    summary: str
    facts: list[dict]
    source_ids: list[str]
    open_questions: list[str]
```

验收标准：

- Planner 输出经过模型校验。
- SSE 事件使用统一模型。
- 不再在核心流程中大量使用无约束的 `dict[str, Any]`。
- 缺少任务标题、意图或查询时能够返回明确错误。

### 3.3 拆分 `main.py`

当前 `backend/src/main.py` 职责过多，需要拆分为：

```text
backend/src/
├── main.py
├── config.py
├── models.py
├── prompts.py
├── agent.py
└── services/
    ├── llm.py
    ├── search.py
    ├── planner.py
    ├── summarizer.py
    └── reporter.py
```

职责：

```text
main.py
  -> FastAPI 路由、CORS、依赖注入

config.py
  -> 环境变量、默认值、配置校验

models.py
  -> Pydantic 数据模型

prompts.py
  -> Planner、Summarizer、Reporter Prompt

services/llm.py
  -> Tokeness OpenAI SDK、超时、重试、错误分类

services/search.py
  -> Tavily、结果标准化、去重

services/planner.py
  -> 研究计划生成和校验

services/summarizer.py
  -> 任务级总结

services/reporter.py
  -> 最终报告生成和引用校验

agent.py
  -> 研究流程编排
```

验收标准：

- `main.py` 不再直接实现完整研究流程。
- LLM 和搜索服务可以单独 Mock 测试。
- Prompt 可以独立修改和版本管理。
- 服务之间通过结构化模型传递数据。

## 4. P1：核心链路完善

### 4.1 增加任务级 SSE 事件

当前只有通用状态消息，目标是增加明确的事件类型：

```text
research_started
plan_created
task_started
search_started
search_completed
summary_started
summary_completed
task_completed
report_started
report_completed
research_failed
research_completed
```

事件示例：

```json
{
  "event_id": "evt-001",
  "type": "task_completed",
  "research_id": "r-001",
  "task_id": "task-002",
  "progress": 48,
  "message": "任务总结完成",
  "source_count": 5
}
```

前端需要展示：

- 任务列表
- 任务标题
- 当前任务状态
- 每个任务的来源数
- 每个任务的摘要状态
- 完整进度日志

### 4.2 增加任务级失败隔离

目标：一个任务失败时，其他任务继续执行。

```text
任务 1：completed
任务 2：failed
任务 3：completed
任务 4：completed
  -> 报告中标记任务 2 资料缺失
```

只有以下情况终止整体研究：

- 规划阶段失败
- 所有任务都失败
- 报告阶段失败且无法重试
- 超过研究总超时
- 用户主动取消

### 4.3 建立来源注册表

所有来源进入系统时分配稳定 ID：

```text
S001, S002, S003, ...
```

模型上下文统一格式：

```text
[S001]
标题：...
URL：...
摘要：...
```

任务摘要只引用：

```json
{
  "source_ids": ["S001", "S003"]
}
```

报告生成后校验：

- 来源 ID 是否存在
- 是否引用了低质量或被过滤来源
- 是否出现不存在的引用编号
- 关键事实是否有来源

### 4.4 增加总超时预算

当前只有单次 LLM 和搜索请求超时，需要增加整个研究的总预算：

```env
RESEARCH_TOTAL_TIMEOUT=600
TASK_TIMEOUT=120
```

建议优先级：

```text
研究总超时
  > 单任务超时
  > 单个搜索超时
  > 单次 LLM 超时
```

## 5. P1：Redis 上下文工程

在任务级摘要和数据模型完成后引入 Redis。

### 5.1 Redis 第一阶段职责

先实现：

- 研究运行时状态
- 任务状态
- 查询结果缓存
- 任务摘要缓存
- SSE 事件缓存

暂时不优先实现：

- 复杂向量记忆
- 全量网页正文长期保存
- 跨租户共享私有网页数据

### 5.2 Redis Key

```text
research:{research_id}
research:{research_id}:tasks
research:{research_id}:events
task:{research_id}:{task_id}
query:{query_hash}
summary:{task_hash}
lock:research:{research_id}
```

### 5.3 查询缓存

查询缓存 Key 应包含：

- 规范化 query
- 搜索 Provider
- 搜索深度
- 最大结果数
- 搜索适配器版本

缓存结果应包含：

- 结果列表
- 来源 ID
- 创建时间
- 过期时间
- Provider 名称

建议初始 TTL：

```text
实时主题：5 分钟到 1 小时
普通主题：6 小时到 24 小时
稳定知识：1 天到 7 天
```

### 5.4 网页缓存

网页缓存 Key：

```text
page:{sha256(normalized_url)}
```

网页内容需要保存：

- 规范化 URL
- 页面标题
- 清洗后的正文
- 内容哈希
- 抓取时间
- HTTP 状态码
- 质量分数
- 解析器版本

### 5.5 上下文预算

不要把完整对话历史传给每个 Agent。

```text
Planner：主题 + 用户要求 + 少量历史摘要
Searcher：任务 query + 搜索配置
Summarizer：任务信息 + 过滤后的来源
Reflection：任务摘要 + 质量统计 + 未解决问题
Reporter：任务摘要 + 来源注册表
```

建议初始预算：

```env
MAX_CONTEXT_TOKENS=16000
LLM_PLAN_MAX_TOKENS=800
LLM_TASK_MAX_TOKENS=1500
LLM_REPORT_MAX_TOKENS=2500
```

上下文超限时依次执行：

```text
去重
  -> 删除低质量来源
  -> 删除低相关性来源
  -> 使用来源摘要替代正文
  -> 使用任务摘要替代原始结果
```

## 6. P2：状态机和研究任务管理

### 6.1 增加 `research_id`

目标 API：

```text
POST /api/research
GET  /api/research/{research_id}
GET  /api/research/{research_id}/stream
POST /api/research/{research_id}/cancel
GET  /api/research/{research_id}/report
```

创建研究返回：

```json
{
  "research_id": "r-20260910-001",
  "status": "created"
}
```

### 6.2 研究状态

```text
CREATED
  -> PLANNING
  -> PLAN_VALIDATED
  -> TASKS_QUEUED
  -> SEARCHING
  -> FILTERING
  -> SUMMARIZING
  -> TASK_COMPLETED
  -> REFLECTING
       ├── FOLLOW_UP_REQUIRED -> TASKS_QUEUED
       └── REPORTING
  -> COMPLETED
```

异常状态：

```text
任意运行状态 -> FAILED
任意运行状态 -> CANCEL_REQUESTED -> CANCELLED
```

### 6.3 状态恢复

Worker 重启后根据 Redis 或数据库中的状态恢复：

```text
SEARCHING
  -> 有搜索结果：进入 FILTERING
  -> 无结果且未超重试：重新搜索
  -> 超过重试次数：标记任务失败
```

不得依赖进程内存恢复研究。

## 7. P2：搜索重试和三级降级

### 7.1 统一搜索 Provider

定义统一接口：

```python
class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, options: SearchOptions) -> SearchResponse:
        ...
```

配置：

```env
SEARCH_PRIMARY=tavily
SEARCH_FALLBACKS=duckduckgo,baidu
SEARCH_MAX_PROVIDER_ATTEMPTS=2
```

推荐初始顺序：

```text
Tavily -> DuckDuckGo -> Baidu
```

中文主题可以根据实际评测调整为：

```text
Tavily -> Baidu -> DuckDuckGo
```

### 7.2 错误分类

可重试并考虑降级：

- 连接超时
- 读取超时
- 网络失败
- 429
- 500、502、503、504
- 空结果
- 返回结构无法解析

不应无意义重试：

- 401 API Key 错误
- 403 权限错误
- 404 地址错误
- 参数校验失败
- 明确额度耗尽

### 7.3 指数退避

```python
delay = min(
    base_delay * (2 ** attempt) + random_jitter,
    max_delay,
)
```

初始配置：

```env
SEARCH_BASE_RETRY_DELAY=1
SEARCH_MAX_RETRY_DELAY=30
```

如果响应中有 `Retry-After`，优先使用该值。

### 7.4 降级事件

需要向日志和 SSE 推送：

```json
{
  "type": "provider_fallback",
  "from": "tavily",
  "to": "duckduckgo",
  "reason": "timeout",
  "attempt": 2
}
```

## 8. P2：网页质量过滤

### 8.1 过滤流程

```text
搜索结果
  -> URL 规范化
  -> 页面类型过滤
  -> 相关性评分
  -> 来源权威性评分
  -> 内容完整性评分
  -> 时效性评分
  -> 广告和导航噪声检测
  -> 内容去重
  -> 保留高质量来源
```

### 8.2 第一版规则

先实现确定性规则：

- URL 去重
- 内容为空或过短过滤
- 标题重复过滤
- 域名黑名单
- 登录页过滤
- 广告和导航页过滤
- 明显无关页面过滤

个人博客、论坛和社交媒体不应直接删除，可以降低质量分数后保留。

### 8.3 质量评分

```text
quality_score =
    0.35 * relevance_score
  + 0.25 * authority_score
  + 0.15 * completeness_score
  + 0.15 * freshness_score
  + 0.10 * independence_score
  - noise_penalty
```

初始配置：

```env
MIN_SOURCE_QUALITY_SCORE=0.55
MIN_SOURCE_RELEVANCE_SCORE=0.50
MAX_SOURCES_PER_TASK=8
ENABLE_SOURCE_FILTER=true
```

“过滤 60% 劣质网页”只能作为待验证目标，不应写成固定保证。需要通过人工标注数据集评估误删率和命中率。

## 9. P2：ReflectionAgent 和补充检索

反思阶段输入：

- 研究主题
- 任务列表
- 任务级摘要
- 来源质量统计
- 未解决问题
- 事实冲突

反思阶段输出：

```json
{
  "sufficient": false,
  "missing_aspects": ["缺少官方数据"],
  "follow_up_queries": ["... official statistics"],
  "confidence": 0.68
}
```

建议配置：

```env
ENABLE_REFLECTION=true
MAX_RESEARCH_LOOPS=3
```

需要防止无限循环：

- 限制最大循环次数
- 限制总 Token 预算
- 限制总搜索次数
- 相同查询不得重复执行
- 没有新增信息时强制进入报告阶段

## 10. P2：长期记忆

### 10.1 记忆类型

来源质量记忆：

```json
{
  "domain": "example.com",
  "quality_score": 0.82,
  "successful_uses": 12,
  "failed_uses": 2
}
```

主题知识记忆：

```json
{
  "topic": "生成式 AI 教育应用",
  "summary": "...",
  "source_ids": ["S001", "S007"]
}
```

查询质量记忆：

```json
{
  "query": "generative AI education applications",
  "backend": "tavily",
  "useful_source_rate": 0.88
}
```

### 10.2 记忆策略

不要将全部历史记忆塞入 Prompt：

```text
当前主题
  -> 检索相关历史摘要
  -> 按相关性和新鲜度排序
  -> 选择少量记忆
  -> 注入 Planner 或 Reflection
```

只有通过来源质量和敏感信息检查的结果才写入长期记忆。

## 11. P2：后台 Worker 和任务取消

长时间研究不应长期占用 FastAPI 请求生命周期。

目标流程：

```text
POST /api/research
  -> 创建状态
  -> 投递 ResearchJob
  -> 返回 research_id

Worker
  -> 执行研究
  -> 写入 Redis
  -> 发布事件

SSE
  -> 读取事件
  -> 推送前端
```

初期可以使用 FastAPI BackgroundTasks，生产环境建议使用 Celery、RQ、Arq 或其他可靠队列。

需要支持：

- 用户取消研究
- Worker 重启恢复
- 任务超时自动取消
- 释放 HTTP 客户端和锁
- 避免同一研究重复执行

## 12. 测试计划

优先添加不依赖真实 API Key 的 Mock 测试：

- Planner JSON 提取和字段校验
- Summarizer 输出校验
- Reporter 引用校验
- Tavily 结果标准化
- URL 规范化和去重
- Redis 缓存命中和过期
- 超时重试
- 429 和 5xx 降级
- 状态机合法转移
- 非法状态转移拒绝
- SSE 事件格式
- SSE 断线恢复
- 任务级失败隔离
- 总超时取消

后续增加离线评测集：

- 固定研究主题
- 固定搜索结果快照
- 人工标注来源质量
- 人工标注关键事实
- 报告引用正确性
- 报告完整性

## 13. 生产级配置草案

```env
# Research limits
MAX_RESEARCH_TASKS=4
MAX_RESULTS_PER_TASK=5
MAX_RESEARCH_LOOPS=3
RESEARCH_TOTAL_TIMEOUT=600
TASK_TIMEOUT=120

# Context engineering
REDIS_URL=redis://localhost:6379/0
SEARCH_CACHE_TTL=21600
PAGE_CACHE_TTL=86400
SUMMARY_CACHE_TTL=86400
EVENT_CACHE_TTL=3600
MAX_CONTEXT_TOKENS=16000

# Search resilience
SEARCH_PRIMARY=tavily
SEARCH_FALLBACKS=duckduckgo,baidu
SEARCH_MAX_PROVIDER_ATTEMPTS=2
SEARCH_BASE_RETRY_DELAY=1
SEARCH_MAX_RETRY_DELAY=30
TAVILY_TIMEOUT=60

# LLM resilience
LLM_PLAN_TIMEOUT=60
LLM_TASK_TIMEOUT=120
LLM_REPORT_TIMEOUT=180
LLM_PLAN_MAX_TOKENS=800
LLM_TASK_MAX_TOKENS=1500
LLM_REPORT_MAX_TOKENS=2500
UPSTREAM_RETRIES=2

# Source quality
MIN_SOURCE_QUALITY_SCORE=0.55
MIN_SOURCE_RELEVANCE_SCORE=0.50
MAX_SOURCES_PER_TASK=8
ENABLE_SOURCE_FILTER=true

# Reflection and memory
ENABLE_REFLECTION=true
ENABLE_LONG_TERM_MEMORY=false

# Observability
LOG_LEVEL=INFO
LOG_FILE=
ENABLE_METRICS=true
```

## 14. 实施顺序

### Phase 1：稳定当前链路

- [x] 实现 `SummarizerAgent`。
- [x] 增加 `models.py` 和结构化数据模型。
- [x] 拆分 `main.py`。
- [x] 增加任务级 Prompt 和版本号。
- [x] 最终报告只读取任务摘要。
- [x] 增加来源 ID 和引用校验。
- [ ] 增加研究总超时。

### Phase 2：完善前后端研究状态

- [ ] 增加 `research_id`。
- [ ] 增加任务级状态。
- [ ] 增加任务级 SSE 事件。
- [ ] 增加前端任务列表和进度日志。
- [ ] 增加任务级失败隔离。
- [ ] 增加取消研究接口。
- [ ] 增加研究状态查询接口。

### Phase 3：引入 Redis 上下文工程

- [ ] 接入 Redis。
- [ ] 保存研究运行时状态。
- [ ] 实现查询结果缓存。
- [ ] 实现网页内容缓存。
- [ ] 实现任务摘要缓存。
- [ ] 实现 SSE 事件缓存。
- [ ] 增加缓存命中率指标。
- [ ] 增加上下文 Token 预算。

### Phase 4：提升搜索稳定性和质量

- [ ] 抽象 `SearchProvider`。
- [ ] 实现 Tavily Provider。
- [ ] 实现 DuckDuckGo fallback。
- [ ] 评估并实现 Baidu fallback。
- [ ] 增加错误分类。
- [ ] 增加指数退避。
- [ ] 增加 URL 和内容去重。
- [ ] 增加网页质量规则过滤。
- [ ] 增加质量评分和来源统计。

### Phase 5：完整 Deep Research

- [ ] 实现 `ReflectionAgent`。
- [ ] 实现补充检索循环。
- [ ] 增加长期记忆。
- [ ] 增加受控并发搜索。
- [ ] 引入后台 Worker。
- [ ] 支持 SSE 断线恢复。
- [ ] 支持历史研究查询。
- [ ] 增加完整自动化测试和离线评测。

## 15. 每次开发后的更新要求

完成任何一项任务后，必须更新本文档：

1. 将对应 `- [ ]` 改为 `- [x]`。
2. 记录实际改动文件。
3. 记录测试命令和结果。
4. 记录未解决问题。
5. 如果调整架构，补充到 `gap.md`。

更新记录格式：

```markdown
### YYYY-MM-DD：任务名称

- 状态：已完成 / 部分完成 / 阻塞
- 修改文件：`path/to/file.py`
- 验证命令：`具体命令`
- 验证结果：通过 / 失败
- 未解决问题：...
```

## 16. 首个执行任务

下一次开发优先执行：

```text
实现任务级 SummarizerAgent，并将最终报告输入改为任务级摘要。
```

执行范围：

1. 增加 `ResearchTask`、`SearchSource`、`TaskSummary` 模型。
2. 增加 Summarizer Prompt。
3. 每个任务搜索完成后调用一次 SummarizerAgent。
4. 给来源分配稳定 ID。
5. 最终 Reporter 只接收任务摘要和来源注册表。
6. 增加任务总结阶段 SSE 事件。
7. 添加 Mock 测试。
8. 更新本文件的 Phase 1 勾选项。

首个任务完成前，暂不优先实现：

- 长期记忆
- 复杂 ReflectionAgent
- 大规模并发搜索
- 多租户缓存
- 复杂向量数据库

## 17. 2026-09-12：完成任务级总结第一阶段

- 状态：部分完成
- 修改文件：
  - `backend/src/main.py`
  - `backend/src/models.py`
  - `backend/src/prompts.py`
  - `backend/src/services/llm.py`
  - `backend/src/services/search.py`
  - `backend/src/services/planner.py`
  - `backend/src/services/summarizer.py`
  - `backend/src/services/reporter.py`
  - `backend/tests/test_pipeline.py`
  - `backend/.env.example`
- 已完成：
  - 每个研究任务独立执行搜索和任务总结。
  - 最终报告只接收任务级摘要和来源注册表。
  - 来源分配稳定的 `S001`、`S002` 编号。
  - 报告生成后检查未注册来源引用。
  - 增加任务级 SSE 事件：任务开始、搜索开始、搜索完成、总结开始、总结完成、任务完成和报告完成。
  - 增加 Planner、Summarizer、Reporter 的服务拆分。
  - 增加 Mock 测试覆盖 JSON 解析、引用校验和完整任务级事件链路。
- 验证命令：
  - `python -m unittest discover -s tests -v`
  - `python -m compileall -q src tests run.py`
  - `npm run build`
- 验证结果：以上检查通过。
- 未完成：
  - 研究总超时和任务总超时。
  - Redis 运行时状态和缓存。
  - 前端任务列表和完整日志展示。
  - 搜索 Provider 降级和网页质量过滤。
