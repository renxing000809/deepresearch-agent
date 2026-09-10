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
