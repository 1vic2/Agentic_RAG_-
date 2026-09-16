# AgenticRAG

一个面向企业文档的多源知识库问答系统。项目使用 **FastAPI + Vue 3 + LangGraph + ChromaDB**，将文档解析、向量检索、重排、知识图谱、联网搜索和可追溯回答串成一个可运行的 RAG 应用。

> 项目定位：适合作为 Agentic RAG、LangGraph 工作流、SSE 流式交互和知识库工程化的学习与面试项目。

![系统架构概览](Architecture%20Overview.jpg)

![系统流程图](Flow%20Chart.jpg)

## 项目亮点

- **知识库全生命周期**：创建、上传、删除、索引、重建和按知识库隔离检索。
- **混合信息来源**：本地 Chroma 向量检索、BGE-M3 嵌入、BGE Reranker 重排、Neo4j 图谱和 Tavily 联网搜索。
- **两种 Agent 工作模式**：
  - 快速模式：LLM 规划工具路线后按顺序执行，延迟和成本更可控。
  - 深度模式：LangGraph 受控 ReAct 循环，执行 `decide → act → observe → decide`，最多调用 3 个不同工具。
- **可靠的流式问答**：SSE 推送状态、工具开始/完成、token、错误和最终证据。
- **可追溯回答**：回答中的 `[n]` 引用可以定位到对应证据卡片。
- **工程化边界**：请求级 `kb_id` 隔离、SQLite 会话、稳定向量片段 ID、上传路径校验、取消请求和模型就绪检查。
- **可评测**：提供 34 道固定题集，覆盖事实题、跨文档题、关系题、追问和拒答题。

## 技术栈

| 层次 | 技术 | 作用 |
| --- | --- | --- |
| Web API | FastAPI、Uvicorn、Pydantic | REST API、SSE、请求校验 |
| Agent 编排 | LangGraph、LangChain Core | 快速路由与深度 ReAct 状态图 |
| 大语言模型 | OpenAI 兼容 API | 工具决策和最终答案生成 |
| 文档处理 | pypdf、LangChain Text Splitters | 多格式解析、切片和元数据保留 |
| Embedding | BGE-M3、FlagEmbedding、PyTorch | 文档和查询向量化 |
| Reranking | BGE Reranker v2 M3 | 对候选证据重新排序 |
| 向量数据库 | ChromaDB | 本地向量持久化和相似度搜索 |
| 图数据库 | Neo4j | 实体关系存储和图谱查询 |
| Web Search | Tavily | 实时联网搜索 |
| Frontend | Vue 3、TypeScript、Vite | 聊天、知识库和图谱管理界面 |
| Visualization | D3.js Canvas | 知识图谱力导向可视化 |
| Streaming | sse-starlette、Fetch SSE parser | 检索过程和回答流式传输 |
| Testing | Python unittest、Vitest | 后端契约测试和前端交互测试 |

## 整体工作流程

### 1. 文档入库和索引

```text
上传文件
  ↓
文件名和扩展名校验
  ↓
DocumentLoader 解析文本
  ↓
文本切片并保留 source / kb_id
  ↓
BGE-M3 生成向量
  ↓
写入 ChromaDB
  ↓
可选：LLM 抽取实体关系 → Neo4j
```

同一个知识库重建索引时，系统使用稳定的片段 ID 清理旧片段，避免重复追加；不同知识库的向量查询通过 `kb_id` 过滤。

### 2. 快速模式

```text
用户问题
  ↓
LLM 规划工具路线
  ↓
vector / graph / web 按路线执行
  ↓
收集证据
  ↓
LLM 根据证据生成带 [n] 引用的答案
```

快速模式适合普通事实查询和对延迟敏感的场景。规划结果经过 allowlist、去重和回退校验，非法输出会回退到向量检索。

### 3. 深度 ReAct 模式

```text
用户问题
  ↓
decide：模型选择工具或结束
  ↓
act：执行 vector / graph / web
  ↓
observe：工具结果写回状态
  ↓
decide：模型根据新证据继续判断
  ↓
最多 3 轮，或模型输出 final
  ↓
统一生成最终回答
```

当前 ReAct 是有界实现：

- 每次最多 3 个工具轮次。
- 同一个工具不会重复调用。
- `use_web=false` 或未配置 Tavily 时不会暴露 web 工具。
- 每个工具都使用当前请求的 `kb_id`。
- 工具失败会记录失败时间线，同时保留已获得证据。
- ReAct 决策失败会回退到普通向量检索。
- 深度 ReAct 模式不会再叠加固定的 `retry_retrieval`，避免重复检索。

### 4. SSE 流式过程

前端请求 `POST /api/query/stream` 后，后端会按顺序推送：

```text
start
  ↓
status: 检索中
  ↓
tool_start / tool_end
  ↓
status: 生成回答
  ↓
token × N
  ↓
done(answer, evidence)
```

异常时会推送 `error`，随后仍发送 `done`，前端可以把失败内容和工具状态保留在当前会话中。

## 效果展示

### 界面功能

| 页面 | 展示内容 |
| --- | --- |
| 智能问答 | 知识库选择、快速/ReAct 深度模式、联网开关、补检索开关、流式回答 |
| 证据面板 | 来源文件、相似度、证据正文、可点击 `[n]` 引用 |
| 工具时间线 | 向量、图谱、联网和 ReAct 工具的运行中、完成、失败状态 |
| 知识库 | 创建知识库、拖拽上传、多格式文档列表、索引和删除 |
| 知识图谱 | Neo4j 实体关系、节点/关系统计、D3.js 缩放和拖拽 |
| 本地诊断 | 模型文件、Python 核心模块和 `/health/ready` 状态检查 |

### 已完成的本地验证

- 后端单元测试：**59 项通过**。
- 前端 Vitest：**13 项通过**。
- 前端 TypeScript 检查和 Vite 生产构建：**通过**。
- Python `compileall`：**通过**。
- 固定题集离线校验：**34 道题通过格式和来源配置检查**。
- 本地 BGE-M3 和 Reranker：已实际完成预热和向量检索。
- 演示知识库的 31 道有预期来源题：来源命中 **31/31**。
- SSE 实际验证：能收到工具开始、工具结束、错误和完成事件。
- 当前外部 LLM 连接曾返回 `Connection error`，因此尚未宣称真实生成质量提升；真实 LLM 质量需要运行固定题集进行 quick / deep 对照。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 一个 OpenAI 兼容的 LLM API
- BGE-M3 和 BGE Reranker 模型
- Neo4j 可选：不开启图谱时可以不启动
- Tavily 可选：不开启联网搜索时可以不配置

后端必须从**项目根目录**启动，因为 `.env` 和本地模型相对路径按根目录解析。

### 安装依赖

```powershell
# 后端
python -m pip install -r backend/requirements.txt

# 复杂 Office / 邮件格式的可选解析依赖
python -m pip install -r backend/requirements-docs.txt

# 前端
Set-Location frontend
npm install
```

如果使用 Conda：

```powershell
conda activate DLPR
python -m pip install -r backend/requirements.txt
```

DLPR 环境需要包含 FastAPI、Uvicorn、LangChain、LangGraph、ChromaDB 和 FlagEmbedding 等核心模块。可以先运行本地诊断脚本。

### 配置

复制模板：

```powershell
Copy-Item backend/.env.example .env
```

按实际环境修改：

```env
OPENAI_API_KEY=your-key
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

TAVILY_API_KEY=
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# 已有本地模型时可以使用项目内路径
BGE_MODEL_PATH=models/bge-m3
BGE_RERANKER_PATH=models/bge-reranker-v2-m3
HF_HUB_OFFLINE=false

HOST=0.0.0.0
PORT=8000
```

不要提交真实 `.env` 或任何 API 密钥；项目已将它们加入 `.gitignore`。

### 方式一：一键本地启动

Windows PowerShell：

```powershell
./scripts/check-local.ps1 -Python ''C:\path\to\python.exe''
./scripts/run-local.ps1 -Python ''C:\path\to\python.exe''
```

脚本会检查核心模块和本地模型文件，启动后端和 Vite，等待：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`
- 就绪检查：`http://127.0.0.1:8000/health/ready`

按 Ctrl+C 只停止脚本自己启动的进程。日志写入被 Git 忽略的 `data/local-run/`。

### 方式二：分别启动

终端一：

```powershell
python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8000
```

终端二：

```powershell
Set-Location frontend
npm run dev
```

打开 `http://127.0.0.1:5173`，创建知识库 → 上传文档 → 索引 → 开始问答。

## 使用示例

### 创建知识库

```powershell
$body = @{name=''产品文档''; description=''内部产品资料''} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/knowledge-bases -Method Post -ContentType ''application/json'' -Body $body
```

### 问答请求

```json
{
  "question": "查询网关默认多久超时？",
  "conversation_id": "demo-session",
  "kb_id": "your-kb-id",
  "use_web": false,
  "deep_mode": false,
  "retry_retrieval": false
}
```

深度 ReAct 只需将 `deep_mode` 改为 `true`：

```json
{
  "question": "哪个团队负责维护平台？",
  "kb_id": "your-kb-id",
  "deep_mode": true,
  "use_web": false
}
```

### 固定题集评测

```powershell
# 先检查题集
python -m evals.run --validate

# quick：快速顺序路由
python -m evals.run --kb-id your-kb-id --mode quick --output data/eval-quick.json

# deep：受控 ReAct
python -m evals.run --kb-id your-kb-id --mode deep --output data/eval-deep-react.json

# 补检索对照实验
python -m evals.run --kb-id your-kb-id --mode quick --retry-retrieval --output data/eval-quick-retry.json
```

评测脚本不会自动上传文件，也不会改动已有知识库。它会输出按题型聚合的来源命中、参考短语匹配、拒答判断和耗时；这些指标不能替代人工或 LLM judge 的事实性评估。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | API 进程健康 |
| GET | `/health/ready` | 嵌入模型是否就绪 |
| POST | `/query` | 非流式问答 |
| POST | `/query/stream` | SSE 流式问答 |
| POST | `/knowledge-bases` | 创建知识库 |
| GET | `/knowledge-bases` | 知识库列表 |
| POST | `/knowledge-bases/{id}/upload` | 上传文档 |
| GET | `/knowledge-bases/{id}/documents` | 文档列表 |
| POST | `/knowledge-bases/{id}/index` | 建立向量索引 |
| POST | `/knowledge-bases/{id}/graph/build` | 构建知识图谱 |
| GET | `/knowledge-bases/{id}/graph` | 获取图谱 |
| GET | `/knowledge-bases/index/status` | 索引统计 |

## 项目结构

```text
AgenticRAG/
├── backend/src/
│   ├── main.py                    # FastAPI API、SSE、检索入口
│   ├── models.py                  # 请求模型
│   ├── agent/
│   │   ├── react_agent.py         # 深度 ReAct：decide/act/observe 循环
│   │   ├── orchestrator.py        # 快速模式顺序工具路由
│   │   ├── retry_policy.py        # 可选的一次指代补检索
│   │   └── routing.py             # 路线过滤和状态转移
│   ├── rag/
│   │   ├── loader.py              # 文档解析和切片
│   │   ├── embedder.py            # BGE-M3
│   │   ├── retriever.py           # 向量检索和 Reranker
│   │   └── store.py               # ChromaDB
│   ├── services/
│   │   ├── graph_service.py       # Neo4j 图谱服务
│   │   ├── index_service.py       # 索引编排
│   │   ├── session_service.py     # SQLite 会话
│   │   ├── tool_progress.py       # SSE 工具进度
│   │   └── web_search.py          # Tavily 结果标准化
│   └── tests/                     # 后端契约和集成测试
├── frontend/src/
│   ├── views/HomeView.vue         # 聊天和 ReAct 控制
│   ├── views/KBView.vue           # 知识库管理
│   ├── views/GraphView.vue        # 图谱可视化
│   ├── components/MarkdownViewer.vue
│   └── utils/sse.ts               # SSE 解析和会话状态
├── evals/                         # 固定题集、夹具和评测脚本
├── scripts/
│   ├── check-local.ps1            # 只读环境诊断
│   └── run-local.ps1              # 一键本地启动
├── docs/                          # 面试指南、设计和联调记录
├── Architecture Overview.jpg
├── Flow Chart.jpg
└── docker-compose.yml
```

## 常见问题

### 为什么前端不是 React？

本项目当前前端使用 Vue 3 + TypeScript；React 是参考项目的前端技术，不是本项目依赖。

### 项目是否使用 ReAct？

是。深度模式使用 LangGraph 手动构建的受控 ReAct 状态图；快速模式仍是固定路线的 Plan-and-Execute。两者共用向量、图谱、联网工具和证据格式。

### 没有 Neo4j 能不能运行？

可以。基础文档上传、索引、向量检索和问答不依赖 Neo4j；只有构建/查询图谱时需要 Neo4j。

### 没有 Tavily 能不能运行？

可以。将 `use_web=false`，或不配置 `TAVILY_API_KEY`，系统仍可使用向量和图谱工具。

## 当前边界

- 真实生成质量取决于可用的 OpenAI 兼容 LLM；本地检索命中不等于答案事实性。
- ReAct 最多三轮且禁止重复工具，优先控制成本和延迟；没有独立的答案反思或 LLM judge。
- 图谱查询目前是通用参数化关系查询，还没有实体链接和多跳路径规划。
- SQLite、文件元数据和本地 ChromaDB 面向单机演示；多进程部署需要集中式会话和任务队列。
- Docker 配置用于可复现部署，本地开发不强制使用 Docker。

## License

MIT
