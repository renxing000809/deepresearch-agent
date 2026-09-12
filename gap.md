# 深度研究架构 Gap 清单

本文档记录当前项目实际实现与 `README.md` 目标设计之间的差异，并给出后续改进建议。

## 1. 当前实际架构

当前系统是一个线性的研究流水线：

```text
Vue 3 前端
    |
    | EventSource / SSE
    v
FastAPI /api/research/stream
    |
    ├── Tokeness LLM：生成研究计划
    |
    ├── Tavily：按研究计划逐个搜索
    |
    ├── 内存：汇总搜索结果和来源
    |
    └── Tokeness LLM：一次性生成最终报告
    |
    v
Vue 3 展示进度和 Markdown 报告
```

当前核心流程：

```text
用户主题
  -> LLM 生成 JSON 研究计划
  -> 串行调用 Tavily
  -> 汇总搜索结果
  -> LLM 生成最终 Markdown 报告
  -> SSE 推送前端
```

当前主要实现文件：

```text
backend/src/main.py
frontend/src/App.vue
```

当前已经具备：

- Vue 3 + TypeScript 前端
- FastAPI 后端
- Tokeness OpenAI-compatible LLM 调用
- Tavily 搜索调用
- SSE 进度推送
- LLM 和 Tavily 超时控制
- 上游超时和网络错误重试
- SSE 心跳
- 前后端错误提示
- `.env` / `.env.example` 配置
- `/api/health` 健康检查

## 2. README 目标架构

README 设计的目标结构如下：

```text
backend/src/
├── agent.py
├── main.py
├── models.py
├── prompts.py
├── config.py
└── services/
    ├── planner.py
    ├── summarizer.py
    ├── reporter.py
    └── search.py
```

目标研究流程：

```text
用户输入主题
  -> FastAPI 创建研究状态
  -> Planner Agent 拆分 TODO
  -> Task Executor 执行每个 TODO
       -> SearchTool 搜索
       -> Summarizer Agent 总结任务
       -> NoteTool 保存任务结果
  -> Reflection Agent 判断知识缺口
  -> 必要时补充搜索
  -> Reporter Agent 生成最终报告
  -> SSE 推送任务、日志、进度和报告
```

## 3. 核心架构 Gap

### 3.1 缺少 Agent 分层

README 设计了独立的研究协调器、规划器、总结器和报告生成器，当前所有逻辑都集中在 `backend/src/main.py`。

当前缺少：

- `ResearchAgent` 或核心协调器
- `PlannerAgent`
- `SummarizerAgent`
- `ReporterAgent`
- 独立的搜索服务
- 独立的 Prompt 模板
- 独立的配置模块
- 独立的数据模型模块

影响：

- 单文件职责过多
- 上游服务难以替换
- 测试难以编写
- 后续添加反思、持久化和并发会变得复杂

建议：

```text
backend/src/
├── agent.py
├── config.py
├── models.py
├── prompts.py
└── services/
    ├── llm.py
    ├── search.py
    ├── planner.py
    ├── summarizer.py
    ├── reporter.py
    └── notes.py
```

### 3.2 缺少任务级总结 Agent

README 中每一个 TODO 都应该经过：

```text
搜索 -> 任务总结 -> 保存笔记
```

当前实际流程是：

```text
搜索 -> 直接保存在内存 -> 最终报告统一总结
```

当前没有针对每个研究任务单独调用 LLM 进行总结。

影响：

- 最终报告 Prompt 过长
- 单条来源缺少结构化摘要
- 任务之间的边界不清晰
- 某个任务失败时无法独立处理
- 更容易触发上下文长度限制和超时

建议：

```text
每个 ResearchTask
  -> Tavily 搜索结果
  -> SummarizerAgent
  -> TaskSummary
  -> 保存到 workspace
```

最终报告只读取任务级摘要，而不是直接读取全部原始搜索内容。

### 3.3 缺少 Reflection Agent

README 提到了反思与知识空白识别，但当前流程只有一轮固定执行：

```text
规划一次 -> 搜索一次 -> 生成报告一次
```

当前没有：

- 判断资料是否足够
- 检查搜索结果是否为空
- 检查来源之间是否冲突
- 识别未覆盖的研究维度
- 自动生成补充查询
- 继续执行第二轮研究

建议增加：

```text
初步任务总结
  -> ReflectionAgent
  -> 判断是否存在知识缺口
  -> 生成补充查询
  -> 再次搜索和总结
```

同时用配置限制最大循环次数，例如：

```env
MAX_WEB_RESEARCH_LOOPS=3
```

### 3.4 缺少 NoteTool 和持久化

README 设计了 `workspace/` 和 `NoteTool`，当前结果只保存在请求生命周期内的内存变量：

```python
findings: list[str] = []
sources: list[dict[str, str]] = []
```

请求结束后，中间结果和报告都会丢失。

当前不支持：

- 查看历史研究
- 查看单个任务摘要
- 恢复中断的研究
- SSE 断线后恢复
- 下载研究笔记
- 重新生成报告
- 对已有研究继续追问

建议增加：

```text
workspace/
└── {research_id}/
    ├── state.json
    ├── plan.json
    ├── tasks/
    │   ├── task-001.json
    │   └── task-002.json
    └── report.md
```

### 3.5 缺少研究状态和任务 ID

README 描述 FastAPI 会创建研究状态，但当前 SSE 请求没有 `research_id`，状态完全绑定在一次 HTTP 连接中。

当前接口：

```text
GET /api/research/stream?topic=...
```

缺少：

- `research_id`
- `task_id`
- 研究创建时间
- 当前阶段
- 当前任务
- 研究状态持久化
- 事件历史
- 取消状态
- SSE 重连点

建议改为：

```text
POST /api/research
GET  /api/research/{research_id}
GET  /api/research/{research_id}/stream
POST /api/research/{research_id}/cancel
```

## 4. 研究流程 Gap

### 4.1 规划结果校验不完整

当前只校验模型输出是否为数组，没有严格校验每个任务的字段。

需要校验：

- `title` 是否存在
- `intent` 是否存在
- `query` 是否存在
- `query` 是否为空
- 任务数量是否在允许范围内
- 任务之间是否重复
- 任务是否覆盖不同研究维度

还需要兼容模型返回 Markdown 代码块的情况：

```text
```json
[...]
```
```

### 4.2 搜索任务是串行执行

当前执行方式：

```python
for task in plan:
    results = await tavily_search(query)
```

任务 1 完成后才会执行任务 2。

影响：

- 总耗时较长
- 一个慢任务会阻塞后续任务
- 深度研究更容易触发整体等待时间

建议使用受控并发：

```text
并发执行 Tavily 搜索
  -> 限制最大并发数
  -> 对单个任务独立捕获异常
  -> 维持任务顺序
  -> 汇总成功和失败结果
```

需要避免无控制地并发，防止触发 Tavily 速率限制。

### 4.3 搜索结果去重不完整

当前只是将结果直接追加到 `sources` 和 `findings`，没有完整去重。

需要处理：

- 相同 URL
- 带不同查询参数的相同页面
- 标题重复
- 内容高度相似
- 多个任务返回同一个来源

建议使用规范化 URL 去重，并保留来源首次出现时的编号。

### 4.4 搜索结果上下文管理不足

当前会把多轮 Tavily 内容拼接到最终报告 Prompt 中。虽然单条内容已经截断，但整体上下文仍可能很大。

风险：

- 输入上下文超限
- Tokeness 处理变慢
- 报告阶段超时
- 费用增加
- 模型注意力分散

建议：

1. 每个任务先做任务级总结。
2. 最终报告只读取任务总结和必要来源。
3. 限制总来源数量。
4. 对重复内容做压缩。
5. 根据模型上下文窗口动态截断。

### 4.5 引用映射不够可靠

当前通过 Prompt 要求模型使用：

```text
[来源序号]
```

但后端没有给每条资料建立强约束的稳定编号，也没有校验报告中的引用编号。

风险：

- 引用编号错位
- 引用不存在的来源
- 事实没有引用
- 引用与事实不匹配
- 模型生成虚假引用

建议在发送给模型前构造固定来源编号：

```text
[S1] 标题：...
URL：...
摘要：...

[S2] 标题：...
URL：...
摘要：...
```

并在报告生成后校验所有引用只能来自已存在的来源编号。

## 5. 超时和可靠性 Gap

### 5.1 当前超时是单请求级别

当前已经加入：

- LLM 规划超时
- LLM 报告超时
- Tavily 超时
- 上游重试
- SSE 心跳

但还缺少完整的研究级超时预算。

例如：

```text
单次 LLM 超时：180 秒
任务数量：4
重试次数：2
```

实际最坏耗时可能非常长。

建议增加：

```env
RESEARCH_TOTAL_TIMEOUT=600
TASK_TIMEOUT=120
```

并在整个研究流程外层增加总超时，避免任务无限等待。

### 5.2 重试策略仍然比较粗

当前对超时和网络错误进行统一重试，但还可以区分：

- 连接超时：可以重试
- 读取超时：可以有限重试
- 429 限流：按照 `Retry-After` 等待
- 401 鉴权失败：不应重试
- 403 权限失败：不应重试
- 404 模型或路径错误：不应重试
- 500/502/503：可以退避重试

建议增加指数退避、状态码分类和最大等待时间。

### 5.3 任务级失败处理不足

当前任意阶段出现异常，整体研究就进入 `error`。

更合理的行为是：

- 单个搜索任务失败时记录失败并继续其他任务
- 报告中标注资料缺失
- 所有任务失败时才终止研究
- 允许用户重试失败任务

## 6. API 和数据模型 Gap

### 6.1 缺少 Pydantic 数据模型

README 设计了 `models.py`，当前没有结构化模型。

建议定义：

```python
class ResearchTask(BaseModel):
    id: str
    title: str
    intent: str
    query: str
    status: str


class SearchSource(BaseModel):
    id: str
    title: str
    url: str
    content: str


class TaskSummary(BaseModel):
    task_id: str
    summary: str
    source_ids: list[str]


class ResearchState(BaseModel):
    research_id: str
    topic: str
    status: str
    progress: int
    tasks: list[ResearchTask]
    report: str | None
    error: str | None
```

### 6.2 `/api/research` 创建接口不完整

之前的项目曾有 `POST /api/research`，当前实际主流程使用的是：

```text
GET /api/research/stream?topic=...
```

这导致：

- 没有先创建研究任务
- 没有返回 `research_id`
- 无法查询研究状态
- 无法恢复 SSE
- 不适合异步后台任务

建议恢复并完善创建接口。

### 6.3 缺少取消接口

当前无法取消正在运行的研究。

建议增加：

```text
POST /api/research/{research_id}/cancel
```

后端应取消当前 asyncio 任务，并释放 HTTP 客户端资源。

## 7. 前端 Gap

### 7.1 前端没有任务列表

README 期望展示所有子任务及其状态，当前前端只展示：

- 总进度百分比
- 当前状态消息
- 最终报告
- 错误信息

缺少：

- 任务列表
- 当前任务高亮
- 每个任务的状态
- 每个任务的来源数
- 每个任务的摘要
- 单任务失败提示

### 7.2 前端没有独立的 SSE composable

README 设计了：

```text
frontend/src/composables/useResearch.ts
```

当前 SSE 逻辑直接写在 `App.vue` 中。

建议抽取：

```typescript
const {
  status,
  progress,
  tasks,
  logs,
  report,
  error,
  start,
  cancel,
} = useResearch()
```

### 7.3 缺少进度日志列表

当前只保留最后一条消息：

```text
正在调用大模型生成研究报告...
```

README 期望展示完整操作日志。

建议在前端维护：

```typescript
type ResearchLog = {
  timestamp: string;
  status: string;
  message: string;
}
```

每次收到 SSE 事件都追加一条日志。

### 7.4 报告没有 Markdown 渲染

当前报告使用 `<pre>` 纯文本展示：

```vue
<pre>{{ report }}</pre>
```

这不会渲染标题、列表、粗体、链接和引用。

建议使用 Markdown 渲染库，例如 `marked`，并对 HTML 输出做安全处理。

### 7.5 前端没有断线重连

当前 SSE 断开后会直接关闭连接并显示错误。

建议：

- 保存 `research_id`
- 记录最后收到的事件 ID
- 自动有限次数重连
- 从后端恢复状态
- 支持用户手动重新连接

## 8. 配置和文档 Gap

### 8.1 README 与实际目录不一致

README 描述有：

```text
agent.py
models.py
prompts.py
config.py
services/
workspace/
```

当前这些文件和目录尚未创建。

### 8.2 README 启动命令过时

README 中部分启动方式是：

```bash
python src/main.py
```

当前推荐方式是：

```bash
cd backend
python run.py
```

当前项目也没有 README 中提到的：

```text
pyproject.toml
```

实际依赖文件是：

```text
backend/requirements.txt
```

### 8.3 README 接口路径不一致

README 中出现：

```text
/research/stream
```

当前实际接口是：

```text
/api/research/stream
```

文档需要统一。

### 8.4 环境变量命名需要统一

当前同时存在通用变量和阶段变量：

```env
LLM_TIMEOUT
LLM_PLAN_TIMEOUT
LLM_REPORT_TIMEOUT
LLM_MAX_TOKENS
LLM_PLAN_MAX_TOKENS
LLM_REPORT_MAX_TOKENS
```

后续应明确优先级，避免用户不知道实际生效的是哪个变量。

## 9. 安全和工程质量 Gap

### 9.1 配置密钥保护

真实 API Key 必须只放在：

```text
backend/.env
```

不能放入：

- `backend/.env.example`
- README
- 日志
- Git 提交
- 前端代码

需要持续检查 `.env.example` 是否只包含占位符。

### 9.2 缺少自动化测试

当前缺少：

- LLM 客户端单元测试
- Tavily 客户端单元测试
- Planner JSON 解析测试
- 超时重试测试
- SSE 事件格式测试
- 健康检查测试
- 前端 SSE composable 测试
- 端到端研究流程测试

建议优先添加不依赖真实 API Key 的 Mock 测试。

### 9.3 缺少请求限制

当前研究接口没有明显限制：

- 单个主题长度之外的限制
- 并发研究数量
- 单 IP 请求频率
- 单用户配额
- 总搜索次数
- 总 Token 使用量

生产环境需要增加限流和配额控制。

### 9.4 缺少结构化日志和请求 ID

当前已有基础日志，但缺少统一的：

- `request_id`
- `research_id`
- `task_id`
- 上游请求耗时
- 上游状态码
- 当前阶段

建议所有日志都携带研究 ID 和任务 ID，便于排查一次研究的完整链路。

## 10. 优先级建议

### P0：优先解决

这些问题直接影响研究可用性和稳定性：

1. 增加任务级总结 Agent。
2. 限制最终报告 Prompt 的总长度。
3. 增加完整的 LLM/Tavily 错误分类。
4. 增加研究总超时。
5. 增加任务级失败处理。
6. 修复并统一 README 启动命令和接口路径。
7. 确保 `.env.example` 不包含真实密钥。

### P1：完善核心架构

1. 拆分 `main.py`。
2. 增加 `models.py`。
3. 增加 `config.py`。
4. 增加 `planner.py`、`summarizer.py`、`reporter.py`、`search.py`。
5. 增加 `research_id` 和 `ResearchState`。
6. 增加 `workspace/` 持久化。
7. 增加稳定来源编号和引用校验。
8. 增加前端任务列表和完整日志。

### P2：实现完整 Deep Research

1. 增加 Reflection Agent。
2. 支持补充检索循环。
3. 支持 SSE 断线重连。
4. 支持取消研究。
5. 增加受控并发搜索。
6. 增加历史研究查询。
7. 增加 Markdown 安全渲染。
8. 增加完整自动化测试。

## 11. 目标架构

建议最终演进为：

```text
FastAPI
  |
  └── ResearchAgent
        |
        ├── PlannerAgent
        │     └── 生成 ResearchTask[]
        |
        ├── TaskExecutor
        │     ├── TavilySearchService
        │     ├── SummarizerAgent
        │     └── NoteService
        |
        ├── ReflectionAgent
        │     └── 判断是否需要补充搜索
        |
        └── ReporterAgent
              └── 生成最终报告
```

建议的 API：

```text
POST /api/research
GET  /api/research/{research_id}
GET  /api/research/{research_id}/stream
POST /api/research/{research_id}/cancel
GET  /api/health
```

建议的最终数据流：

```text
用户主题
  -> 创建 ResearchState
  -> PlannerAgent 生成任务
  -> TaskExecutor 执行任务
       -> Tavily 搜索
       -> SummarizerAgent 生成任务摘要
       -> NoteService 持久化
  -> ReflectionAgent 检查知识缺口
  -> 必要时补充研究
  -> ReporterAgent 生成报告
  -> 保存报告和来源
  -> SSE 推送完整事件流
```

## 12. 结论

当前项目已经完成了最核心的可运行闭环：

```text
Vue 3 + FastAPI + Tokeness + Tavily + SSE
```

但当前更准确的定位是：

```text
LLM 驱动的线性研究流水线
```

README 描述的目标则是：

```text
具备任务总结、笔记持久化、反思循环、研究状态管理和多 Agent 分层的深度研究 Agent
```

两者之间最重要的差距是：

```text
任务级总结 Agent
研究状态管理
NoteTool 持久化
Reflection Agent
稳定的来源引用体系
```

## 13. 生产级架构补充设计

本章节将 Redis、状态机、搜索降级、网页质量过滤、长期记忆和多智能体编排纳入统一的生产级设计。

### 13.1 设计目标

生产版本需要同时满足以下目标：

- 研究流程可恢复、可取消、可重试
- 单个任务失败不影响其他任务
- 上下文长度可控，不依赖全量对话历史
- 相同网页和查询可以跨任务复用
- 搜索服务故障时能够自动降级
- 低质量、重复和无关网页不会直接进入 LLM 上下文
- 任务级中间结果可追踪、可持久化
- 报告中的引用可以追溯到固定来源
- 研究成本、延迟和质量可以量化
- 真实 API Key、用户数据和运行时状态相互隔离

### 13.2 目标总体架构

```text
Vue 3
  |
  | REST + SSE
  v
FastAPI API Layer
  |
  ├── ResearchService
  │     └── 创建、查询、取消、恢复研究
  |
  ├── ResearchOrchestrator
  │     └── 驱动研究状态机
  |
  ├── Agent Layer
  │     ├── PlannerAgent
  │     ├── SearchQueryAgent
  │     ├── SummarizerAgent
  │     ├── ReflectionAgent
  │     └── ReporterAgent
  |
  ├── Tool Layer
  │     ├── SearchTool
  │     ├── PageFetchTool
  │     ├── SourceFilterTool
  │     └── NoteTool
  |
  ├── Context Layer
  │     ├── Redis Runtime State
  │     ├── Query Cache
  │     ├── Page Cache
  │     ├── Summary Cache
  │     └── Event Stream Cache
  |
  ├── Persistence Layer
  │     ├── PostgreSQL 或 SQLite：结构化元数据
  │     ├── Workspace：Markdown 报告和任务笔记
  │     └── Object Storage：大网页内容和附件
  |
  └── External Services
        ├── Tokeness LLM
        ├── Tavily
        ├── DuckDuckGo
        └── Baidu 或其他搜索服务
```

生产环境建议将长时间研究任务放入后台 Worker，而不是让 FastAPI 请求线程直接执行：

```text
POST /api/research
  -> 创建 ResearchState
  -> 投递 ResearchJob
  -> 立即返回 research_id

Worker
  -> 执行状态机
  -> 写入 Redis 和持久化存储
  -> 发布 SSE 事件

GET /api/research/{research_id}/stream
  -> 读取事件并推送前端
```

初期可以使用 FastAPI BackgroundTasks，生产环境建议使用 Celery、RQ、Arq 或其他可靠队列。

## 14. 多智能体编排设计

### 14.1 Agent 职责

```text
ResearchOrchestrator
  ├── PlannerAgent
  │     └── 生成、校验和排序研究任务
  │
  ├── SearchQueryAgent
  │     └── 为任务生成搜索查询和补充查询
  │
  ├── SummarizerAgent
  │     └── 将原始来源压缩为任务级事实摘要
  │
  ├── ReflectionAgent
  │     └── 检查覆盖度、冲突和知识缺口
  │
  └── ReporterAgent
        └── 基于任务摘要生成最终报告
```

### 14.2 Agent 输入输出约束

每个 Agent 必须有明确的输入和输出，不应该共享一个不断增长的完整对话历史。

```text
PlannerAgent
输入：topic、日期、用户要求、历史相关摘要
输出：ResearchTask[]

SummarizerAgent
输入：ResearchTask、FilteredSource[]
输出：TaskSummary

ReflectionAgent
输入：ResearchTask[]、TaskSummary[]、SourceQualityStats
输出：ReflectionResult

ReporterAgent
输入：topic、TaskSummary[]、SourceRegistry
输出：ResearchReport
```

### 14.3 Agent 之间只传递结构化状态

不建议将 Agent 的完整历史消息直接传给下一个 Agent。建议只传递：

- 当前任务
- 当前阶段摘要
- 固定来源编号
- 结构化事实
- 未解决问题
- 质量分数
- Token 预算

示例：

```json
{
  "task_id": "task-002",
  "title": "行业应用现状",
  "facts": [
    {
      "claim": "...",
      "source_ids": ["S003", "S007"],
      "confidence": 0.86
    }
  ],
  "open_questions": ["缺少 2025 年官方数据"],
  "summary": "..."
}
```

### 14.4 多智能体不是无限对话

系统应该采用有限、可观测的编排流程，而不是让多个 Agent 自由互聊：

```text
PlannerAgent
  -> TaskExecutor
  -> SummarizerAgent
  -> ReflectionAgent
  -> Follow-up TaskExecutor（可选）
  -> ReporterAgent
```

每个 Agent 调用都必须有：

- 最大调用次数
- 最大 Token 数
- 单次超时
- 总体超时预算
- 明确失败状态
- 可重试条件

## 15. 研究状态机设计

### 15.1 研究状态

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

异常转移：

```text
任意运行状态 -> FAILED
任意运行状态 -> CANCEL_REQUESTED -> CANCELLED
```

### 15.2 任务状态

```text
PENDING
  -> SEARCHING
  -> FILTERING
  -> SUMMARIZING
  -> COMPLETED

PENDING / SEARCHING / FILTERING / SUMMARIZING
  -> RETRYING
  -> FAILED
  -> SKIPPED
```

### 15.3 状态转移约束

所有状态转移必须经过统一函数，不能在业务代码中随意修改状态：

```python
transition(
    research_id="r-001",
    from_state="SEARCHING",
    to_state="SUMMARIZING",
    reason="search_completed",
)
```

每次转移写入：

```json
{
  "research_id": "r-001",
  "task_id": "task-001",
  "from": "SEARCHING",
  "to": "SUMMARIZING",
  "reason": "search_completed",
  "attempt": 1,
  "timestamp": "2026-09-10T10:00:00Z"
}
```

### 15.4 状态机恢复

Worker 重启后，根据 Redis 或数据库中的状态恢复：

```text
SEARCHING
  -> 检查上一次请求是否有结果
  -> 有结果：进入 FILTERING
  -> 无结果且未超时：重试搜索
  -> 已超出重试次数：标记任务失败
```

不要依赖内存中的 Python 变量恢复研究。

## 16. Redis 上下文工程

### 16.1 Redis 的职责边界

Redis 负责高频、临时、可重建的运行时数据：

- 研究状态
- 任务状态
- 搜索结果缓存
- 网页内容缓存
- 任务摘要缓存
- SSE 事件缓冲
- 分布式锁
- 限流计数器

长期报告和正式研究笔记不建议只存 Redis，应同步保存到数据库、文件系统或对象存储。

### 16.2 Redis Key 设计

```text
research:{research_id}
research:{research_id}:tasks
research:{research_id}:events
research:{research_id}:sources
task:{research_id}:{task_id}
query:{query_hash}
page:{url_hash}
summary:{task_hash}
memory:domain:{domain}
memory:topic:{topic_hash}
lock:research:{research_id}
rate:tavily:{scope}
```

### 16.3 搜索查询缓存

查询缓存 Key 使用规范化查询生成：

```text
query_hash = sha256(
    normalized_query
    + search_backend
    + search_depth
    + max_results
)
```

缓存内容：

```json
{
  "query": "generative AI education applications",
  "backend": "tavily",
  "results": [
    {
      "source_id": "S001",
      "title": "...",
      "url": "...",
      "snippet": "..."
    }
  ],
  "created_at": "...",
  "expires_at": "..."
}
```

建议 TTL：

```text
新闻和实时主题：5 分钟到 1 小时
普通行业主题：6 小时到 24 小时
稳定知识主题：1 天到 7 天
```

### 16.4 网页内容缓存

网页 URL 先经过规范化：

- 删除追踪参数
- 统一协议和域名大小写
- 删除末尾斜杠差异
- 处理 URL 编码
- 保留必要的业务参数

然后使用：

```text
page:{sha256(normalized_url)}
```

缓存中建议同时保存：

- 原始 URL
- 规范化 URL
- 页面标题
- 清洗后的正文
- 内容摘要
- 内容哈希
- 抓取时间
- HTTP 状态码
- 页面质量分数
- 解析器版本

### 16.5 同任务和跨任务去重

同任务去重：

```text
同一个 research_id 内，不重复处理相同 URL 和相同内容哈希。
```

跨任务去重：

```text
优先读取 page:{url_hash} 和 query:{query_hash}，避免重复搜索和抓取。
```

跨任务缓存必须注意数据隔离：

- 公共网页可以跨用户复用
- 私有网页必须按用户或租户隔离
- 包含用户输入的数据不能写入公共缓存

### 16.6 中间摘要缓存

任务摘要写入：

```text
summary:{task_hash}
```

`task_hash` 至少包含：

- 任务标题
- 任务意图
- 查询结果内容哈希
- summarizer prompt 版本
- 模型名称

这样 Prompt 或模型版本改变后，可以自动避免读取旧摘要。

## 17. 上下文预算和状态机替代全量历史

### 17.1 不传递完整对话历史

每个阶段只读取当前需要的上下文：

```text
规划阶段：主题 + 用户要求 + 少量历史摘要
搜索阶段：任务 query + 搜索配置
总结阶段：任务信息 + 过滤后的来源
反思阶段：任务摘要 + 质量统计 + 未解决问题
报告阶段：任务摘要 + 来源注册表
```

### 17.2 Token 预算

建议为每个阶段分配预算：

```text
Planner：输入 4K，输出 800
Task Summarizer：输入 8K，输出 1.5K
Reflection：输入 6K，输出 800
Reporter：输入 16K，输出 2.5K
```

具体数值需要根据模型上下文窗口配置，不应写死在代码中。

### 17.3 上下文压缩顺序

当输入超过预算时，按以下顺序压缩：

```text
1. 删除重复来源
2. 删除低质量来源
3. 删除低相关性来源
4. 使用来源摘要替换正文
5. 使用任务摘要替换原始搜索结果
6. 保留与当前任务最相关的事实
```

不能简单地从字符串尾部截断，因为这可能截断来源 URL 或关键事实。

### 17.4 20 到 30 个网页处理策略

如果需要处理 20 到 30 个网页，不应把全部正文一次性发送给最终报告模型：

```text
20~30 个网页
  -> 页面清洗
  -> 质量评分
  -> 内容去重
  -> 按任务分组
  -> 每组摘要
  -> 任务级摘要
  -> 反思
  -> 最终报告
```

报告模型只读取：

- 任务级摘要
- 关键事实
- 来源编号
- 少量必要原文片段

## 18. 搜索工具重试与降级

### 18.1 搜索服务优先级

建议将搜索后端抽象为统一接口：

```python
class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, options: SearchOptions) -> SearchResponse:
        ...
```

生产配置示例：

```env
SEARCH_PRIMARY=tavily
SEARCH_FALLBACKS=duckduckgo,baidu
SEARCH_MAX_PROVIDER_ATTEMPTS=2
```

推荐默认顺序：

```text
高质量英文或综合主题：Tavily -> DuckDuckGo
中文主题：Tavily -> Baidu -> DuckDuckGo
实时和新闻主题：Tavily -> 其他实时搜索源
```

具体顺序应根据真实可用性、授权和搜索质量验证后确定。

### 18.2 触发降级的错误

触发重试或降级：

- 连接超时
- 读取超时
- DNS 或网络失败
- 429 限流
- 500、502、503、504
- 返回空结果
- 返回不可解析的响应

不应盲目重试：

- 401 API Key 错误
- 403 权限错误
- 404 接口地址错误
- 参数校验失败
- 明确的额度耗尽错误

### 18.3 指数退避

```python
delay = min(
    base_delay * (2 ** attempt) + random_jitter,
    max_delay,
)
```

建议默认值：

```text
base_delay = 1 秒
max_delay = 30 秒
jitter = 0 到 0.5 秒
```

如果上游返回 `Retry-After`，优先使用上游建议的等待时间。

### 18.4 降级事件

每次降级都要记录并推送：

```json
{
  "type": "provider_fallback",
  "from": "tavily",
  "to": "duckduckgo",
  "reason": "timeout",
  "attempt": 2
}
```

报告中可以记录来源后端，但不应把搜索服务错误细节暴露为用户难以理解的技术堆栈。

## 19. 网页质量过滤

### 19.1 过滤流程

```text
搜索结果
  -> URL 规范化
  -> 域名和页面类型过滤
  -> 相关性评分
  -> 来源权威性评分
  -> 内容完整性评分
  -> 时效性评分
  -> 广告和导航噪声检测
  -> 内容去重
  -> 保留高质量来源
```

### 19.2 质量评分模型

```text
quality_score =
    0.35 * relevance_score
  + 0.25 * authority_score
  + 0.15 * completeness_score
  + 0.15 * freshness_score
  + 0.10 * independence_score
  - noise_penalty
```

权重应通过离线评测调整，不应直接认为固定权重适合所有主题。

### 19.3 过滤规则

可以优先过滤：

- 空内容或极短页面
- 纯登录页面
- 纯导航页
- 大量广告和弹窗页面
- URL 和标题明显重复的页面
- 与任务意图低相关的页面
- 无法确认来源的转载聚合页
- 明显的垃圾 SEO 页面

谨慎过滤：

- 个人博客
- 论坛内容
- 社交媒体内容
- 新兴主题的非官方资料

这些页面不一定低质量，应该降低分数而不是简单删除。

### 19.4 质量过滤结果模型

```json
{
  "source_id": "S004",
  "url": "https://example.com/article",
  "relevance_score": 0.91,
  "authority_score": 0.80,
  "freshness_score": 0.76,
  "quality_score": 0.84,
  "is_duplicate": false,
  "is_low_quality": false,
  "filter_reason": null
}
```

“过滤约 60% 劣质网页”只能作为待验证的目标指标，不能作为系统固定保证。应通过固定数据集评估：

```text
过滤前来源数
过滤后来源数
人工标注低质量来源数
过滤命中率
误删率
报告引用有效率
```

## 20. 来源注册表和引用系统

### 20.1 固定来源 ID

所有来源进入上下文前分配固定 ID：

```text
S001, S002, S003, ...
```

模型上下文格式：

```text
[S001]
标题：...
URL：...
来源质量：0.86
摘要：...
```

模型只能使用已存在的来源 ID。

### 20.2 引用校验

报告生成后检查：

- 报告中的来源 ID 是否存在
- 是否引用了被过滤来源
- 是否存在未定义来源 ID
- 关键事实是否至少有一个来源
- 来源 URL 是否可访问

发现非法引用时，可以：

1. 删除非法引用。
2. 重新调用一次引用修复 Agent。
3. 将问题标记到报告质量告警中。

## 21. 长期记忆设计

### 21.1 运行时上下文和长期记忆分离

```text
运行时上下文
  -> Redis
  -> 研究结束后可过期

长期记忆
  -> 数据库、向量库或对象存储
  -> 跨研究复用
```

### 21.2 长期记忆类型

来源质量记忆：

```json
{
  "domain": "example.com",
  "quality_score": 0.82,
  "successful_uses": 12,
  "failed_uses": 2,
  "last_seen_at": "..."
}
```

主题知识记忆：

```json
{
  "topic": "生成式 AI 教育应用",
  "summary": "...",
  "source_ids": ["S001", "S007"],
  "updated_at": "..."
}
```

查询质量记忆：

```json
{
  "query": "generative AI education applications",
  "backend": "tavily",
  "useful_source_rate": 0.88,
  "last_used_at": "..."
}
```

### 21.3 记忆读取策略

不要将所有历史记忆直接放入 Prompt：

```text
当前主题
  -> 检索相关历史摘要
  -> 按相关性和新鲜度排序
  -> 选择少量记忆
  -> 注入 Planner 或 Reflection 上下文
```

### 21.4 记忆写入策略

只有满足以下条件的结果才写入长期记忆：

- 来源质量达到阈值
- 摘要通过结构化校验
- 引用来源可追溯
- 不是明显的临时错误信息
- 没有包含敏感用户数据

## 22. API 和 SSE 生产协议

### 22.1 API

```text
POST /api/research
GET  /api/research/{research_id}
GET  /api/research/{research_id}/stream
POST /api/research/{research_id}/cancel
GET  /api/research/{research_id}/report
GET  /api/health
```

创建研究：

```json
{
  "topic": "生成式 AI 在教育行业的应用趋势",
  "options": {
    "max_tasks": 4,
    "max_results_per_task": 5,
    "enable_reflection": true
  }
}
```

返回：

```json
{
  "research_id": "r-20260910-001",
  "status": "created"
}
```

### 22.2 SSE 事件类型

```text
event: research_started
event: plan_created
event: task_started
event: search_started
event: source_filtered
event: summary_created
event: task_completed
event: reflection
event: provider_fallback
event: heartbeat
event: report_started
event: report_completed
event: research_failed
event: research_completed
```

事件数据示例：

```json
{
  "event_id": "evt-00012",
  "research_id": "r-001",
  "task_id": "task-002",
  "status": "SUMMARIZING",
  "progress": 62,
  "message": "正在生成任务摘要",
  "timestamp": "2026-09-10T10:00:00Z"
}
```

### 22.3 SSE 断线恢复

客户端保存最后一个 `event_id`，重连时发送：

```text
Last-Event-ID: evt-00012
```

后端从 Redis 事件列表中补发之后的事件。

## 23. 可观测性设计

### 23.1 日志字段

所有关键日志应包含：

```text
request_id
research_id
task_id
agent_name
stage
provider
model
attempt
elapsed_ms
status
error_type
```

不要记录：

- API Key
- Authorization Header
- 用户敏感信息
- 未脱敏的私有网页正文

### 23.2 指标

研究指标：

- 研究成功率
- 平均研究耗时
- P95 研究耗时
- 单任务成功率
- 任务重试次数
- 反思触发率

搜索指标：

- 搜索成功率
- 平均响应时间
- P95 响应时间
- 429 比例
- 降级比例
- 缓存命中率
- 每次研究平均来源数

LLM 指标：

- 输入 Token 数
- 输出 Token 数
- 每个 Agent 调用次数
- LLM 超时率
- JSON 解析失败率
- 报告生成成功率

质量指标：

- 来源有效率
- 来源重复率
- 低质量来源过滤率
- 事实引用覆盖率
- 非法引用率
- 人工评价分数

### 23.3 成本指标

每个研究记录：

```text
llm_input_tokens
llm_output_tokens
search_calls
cache_hits
cache_misses
retry_count
fallback_count
estimated_cost
```

缓存带来的“Token 消耗下降 7%”需要使用固定实验集验证，记录优化前后：

- 平均输入 Token
- 平均输出 Token
- 总 Token
- 平均延迟
- 报告质量
- 研究成本

## 24. 安全、限流和数据治理

### 24.1 API Key

真实密钥只允许存在于：

```text
backend/.env
```

禁止进入：

- `.env.example`
- Git 提交
- 前端构建产物
- SSE 数据
- 日志
- 错误堆栈

### 24.2 请求限流

建议限制：

- 单用户同时运行研究数
- 单 IP 创建研究频率
- 单研究最大任务数
- 单任务最大来源数
- 单研究最大搜索次数
- 单研究最大 Token 预算
- 单研究最大运行时间

### 24.3 网页数据治理

网页正文可能包含：

- 用户提交的敏感查询
- 第三方个人信息
- Prompt Injection
- 恶意脚本或恶意指令

网页内容必须作为不可信数据处理：

- 不执行网页中的代码
- 不执行网页中的工具调用指令
- 不把网页内容当作系统 Prompt
- 对 HTML、脚本和嵌入内容进行清洗
- 报告生成时明确“来源内容是外部资料”

## 25. 生产级配置建议

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

# Observability
LOG_LEVEL=INFO
LOG_FILE=
ENABLE_METRICS=true
```

## 26. 实施路线图

### Phase 1：稳定当前链路

1. 拆分 `main.py` 中的 LLM、Tavily 和 SSE 逻辑。
2. 增加结构化 Pydantic 数据模型。
3. 增加任务级总结 Agent。
4. 增加来源固定编号和引用校验。
5. 增加总超时预算和任务级失败处理。
6. 更新 README 的接口和启动文档。

### Phase 2：引入状态和上下文工程

1. 增加 `research_id` 和任务 ID。
2. 引入 Redis 运行时状态。
3. 增加搜索查询缓存。
4. 增加网页内容缓存。
5. 增加任务摘要缓存。
6. 增加状态机和状态恢复。
7. 增加 SSE 事件缓存和断线恢复。

### Phase 3：提升搜索质量和可靠性

1. 抽象统一的 SearchProvider 接口。
2. 增加 Tavily、DuckDuckGo、Baidu 降级链路。
3. 增加指数退避和错误分类。
4. 增加网页质量过滤。
5. 增加 URL、内容和语义去重。
6. 增加来源质量统计。

### Phase 4：完整 Deep Research

1. 增加 ReflectionAgent。
2. 增加补充检索循环。
3. 增加长期记忆。
4. 增加受控并发搜索。
5. 增加后台 Worker。
6. 增加报告版本和历史研究。
7. 增加完整自动化测试和离线评测集。

## 27. 验收标准

生产版本至少应满足：

- 单个搜索任务失败不会直接导致整个研究失败。
- 研究可以通过 `research_id` 查询和恢复。
- SSE 断线后可以从最近事件继续接收。
- 相同查询和网页能够命中缓存。
- 最终报告不会直接携带全部原始网页正文。
- LLM 报告阶段输入 Token 有明确上限。
- 搜索服务出现超时、429 或 5xx 时可以重试或降级。
- 401、403、404 等配置错误不会无意义重试。
- 每个来源具有稳定的来源 ID。
- 报告中的引用均能映射到真实来源。
- 低质量和重复来源在进入 LLM 前被过滤。
- 研究中间结果能够持久化。
- 研究可取消，资源可以释放。
- 日志可以通过 `research_id` 还原完整执行链路。
- API Key 不出现在日志、前端和文档中。
- 有可重复的缓存、Token、延迟和质量对比实验。
