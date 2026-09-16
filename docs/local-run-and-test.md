# 无 Docker 本地启动与联调记录（2026-09-15）

在项目根目录执行后端命令；`.env` 和 `models/...` 相对路径都从这里解析。Windows PowerShell 可用两个终端：

```powershell
# 一键启动；按 Ctrl+C 退出并清理本脚本启动的前后端进程
./scripts/run-local.ps1 -Python 'C:\Users\huiping.liu\AppData\Local\Programs\Python\Python312\python.exe'
```

也可分别启动两个前台终端：

```powershell
# 终端一：使用已安装 backend/requirements.txt 的解释器
python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 8000

# 终端二
Set-Location frontend
npm run dev
```

若 npm 对额外 CLI 参数解析异常，可从 `frontend` 目录直接运行 `./node_modules/.bin/vite.cmd --host 127.0.0.1`。访问 `http://127.0.0.1:5173/`；Vite 将 `/api/...` 代理到后端端口 8000。先检查 `/health/ready` 返回 200 再索引或提问：`/health` 返回 200 只表示 API 进程已启动；模型预热中和预热失败时 `/health/ready` 返回 503。这个接口不检测 LLM、Neo4j 和 Tavily 的连通性。

本机 `E:\miniconda\envs\DLPR` 环境包含 PyTorch，但缺 FastAPI、LangChain、ChromaDB 等核心包；如需使用它，先在 DLPR 中安装 `backend/requirements.txt`。本次联网依赖安装请求未获批准，因此联调使用本机另一个已经具有全部直接依赖的 Python 3.12 解释器，没有修改 DLPR 环境。`.env` 已指向本地 BGE-M3 和重排模型目录；预热与重排成功。

本次 API 联调创建了演示知识库 `a65204b9a85f`，只上传 `evals/fixtures/` 的四个虚构 TXT 文档，索引得到 4 个文档片段。原有知识库和文档未被覆盖。直连后端和 Vite `/api/health` 均返回 200；非流式问答检索返回正确来源和 4 条证据；SSE 依次返回 `start`、`tool_start`、`tool_end`、`error`、`done`，向量工具成功。Neo4j 未在本机监听 7687，上传时返回图谱清理警告；不影响文档索引。

LLM 请求在快模式、深度模式以及 SSE 生成阶段均返回 `Connection error`。深度模式现在走受控 ReAct：默认最多三轮 `decide → tool → observation`，LLM 决策失败时回退到向量检索；本次没有获得可评估的生成回答。当前运行权限下也无法在浏览器自动化工具中打开本地页面，页面只进行了 HTTP、前端单元测试和生产构建检查。

独立的本地向量检索探针遍历了固定题集 34 题：31 道有预期来源的题全部命中（31/31），3 道拒答题不计来源命中。模型首次加载拉高了全程平均耗时；本轮请求的 p95 约 126 ms。来源命中只说明文档进入证据列表，不证明回答正确或忠于证据。缺少有效 LLM 回答和 token 用量，第 4 阶段受限二次检索只作为默认关闭的对照实验，不宣称质量提升。恢复 LLM 连接后用 `python -m evals.run --kb-id a65204b9a85f --mode quick --output data/eval-quick.json` 和同命令加 `--retry-retrieval --output data/eval-quick-retry.json` 对照，再用 `--mode deep` 核对 Agent 模式。

本地诊断命令（只显示配置是否就绪，不显示密钥内容）：

```powershell
./scripts/check-local.ps1 -Python 'C:\Users\huiping.liu\AppData\Local\Programs\Python\Python312\python.exe'
./scripts/check-local.ps1 -Python 'E:\miniconda\envs\DLPR\python.exe'
```

本轮第一条命令返回退出码 0，核心模块、本地模型文件、API 模型就绪检查均为真；DLPR 返回退出码 1，明确列出缺失的后端模块。脚本不安装包、不启动服务，也不检查 LLM/Neo4j/Tavily 的网络连通性。

`run-local.ps1` 在服务已运行时会复用它们；在端口空闲时本轮实际启动了隐藏的后端与 Vite 子进程，并等待两个 HTTP 地址和 BGE-M3 就绪。日志写入被 Git 忽略的 `data/local-run/`。演示库追问 SSE 实际返回一次 `vector` 与一次 `vector_retry` 成功事件（约 66 ms 与 65 ms），两次查询沿用 `a65204b9a85f`。回答生成仍因 LLM 连接失败，不能据此判断二次检索提升回答质量。
