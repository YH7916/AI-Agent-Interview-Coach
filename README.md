# AI Agent Mock Interviewer

这是一个独立的本地 AI Agent 岗模拟面试桌面应用。v1/v2 保留为底层检索与 Agent 演进接口；v3 是最终产品入口，围绕 AI Agent 高频面经提供真实浏览器来源接入、连续模拟面试、prompt-driven 面试官、AI 评价、弱点长期记忆和整场复盘。

## 已实现功能

| 阶段 | 路由 | 实现 |
| ---- | ---- | ---- |
| Phase 1 | `/v1`、`/v1/search`、`/v1/documents` | 解析 HTML 可见文本，使用 BM25/关键词检索，忽略 `script` 等不可见内容 |
| Phase 2 | `/v2`、`/v2/search` | SOP section chunking + embedding vector store + BM25/RRF hybrid retrieval；无密钥时自动使用离线 semantic fallback |
| Phase 3 | `/v3`、`/interview`、`/interview/chat/stream` | AI Agent 岗模拟面试训练：本地/授权网页面经导入、题库结构化、prompt-driven 面试官、流式追问、AI 评价和 L3 弱点记忆 |
| Phase 4 | `/v3/memory`、`/v3/memory/search` | L0-L3 layered memory，支持流式/非流式写入、L1 原子事实、L2 面试场景、L3 偏好/弱点画像、冲突覆盖、过期隐藏、删除和离线 memory eval |

前端是纯静态页面，由 FastAPI 托管；主界面只展示最终产品 `v3 Interview Agent`。`/v1`、`/v2` 作为 v3 的底层演进和验收接口保留，但不在产品入口里并列展示。

## 目录结构

```text
AI-Agent-Interview-Coach/
├── app.py                    # FastAPI 启动入口
├── data/                     # v1/v2 historical demo SOP HTML
├── desktop/                  # Tauri v2 桌面壳，启动 Python sidecar 后打开 /v3
├── evals/interview_agent/    # 产品级 regression / capability / source eval 数据集
├── frontend/                 # 静态前端页面和 ES module 组件
├── oncall_app/
│   ├── api/                  # 路由、schema、静态文件托管
│   ├── agent/                # tool-calling loop、readFile 工具、证据抽取
│   ├── documents/            # v1/v2 HTML 解析、repository、section 抽取
│   ├── interview/            # v3 面试题库、浏览器登录态、面试官 director、评分与复盘
│   ├── evaluation/           # README 验收用 evaluation cases 和 metrics
│   ├── llm/                  # OpenAI-compatible embedding/chat clients
│   ├── memory/               # L0 raw events、L1/L2/L3 memories、SQLite store、recall
│   └── retrieval/            # BM25、chunking、vector store、hybrid retrieval
├── packaging/pyinstaller/    # sidecar 打包 spec
├── scripts/evaluate.py       # 离线验收脚本
├── scripts/evaluate_interview_agent.py
├── scripts/package_desktop.ps1
├── tests/                    # 单元测试、API 测试、检索测试、集成 smoke test
├── requirements.txt
├── requirements-dev.txt
├── package.json
└── pyproject.toml
```

## 快速启动

```powershell
cd D:\Projects\AI-Agent-Interview-Coach
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
npm install
python app.py
```

打开最终产品：

- `http://127.0.0.1:8000/v3`

v3 顶栏按最终产品功能拆成 4 个页面：`面试`、`题库`、`来源`、`复盘`。

如需让“导入默认简历”指向本机固定文件，可设置：

```powershell
$env:INTERVIEW_DEFAULT_RESUME_PATH = "D:\Desktop\CV\your-resume.pdf"
```

底层验收路径仍保留：

- `http://127.0.0.1:8000/v1`
- `http://127.0.0.1:8000/v2`

## 桌面应用打包

真实产品形态是 Tauri 桌面壳 + PyInstaller Python sidecar。用户打开桌面应用后，Rust 壳会选择空闲 localhost 端口，启动 `interview-agent-sidecar`，等待 `/health` 就绪，再打开 `/v3`。

```powershell
cd D:\Projects\AI-Agent-Interview-Coach
powershell -ExecutionPolicy Bypass -File scripts\package_desktop.ps1
```

打包命令会依次执行 ruff、mypy、完整单测、前端 lint、`interview_agent` 全量 eval、PyInstaller sidecar，然后运行 Tauri build。当前环境如果没有 Rust/Cargo，可以先验证 sidecar 和全部 Python/JS/eval 门槛：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_desktop.ps1 -SkipTauriBuild
```

主要产物：

- `dist\interview-agent-sidecar.exe`
- `desktop\src-tauri\binaries\interview-agent-sidecar-x86_64-pc-windows-msvc.exe`
- 完整 Tauri 构建环境下的安装包位于 `desktop\src-tauri\target\release\bundle\`

## 离线验收

默认测试不访问外部网络，未配置真实模型密钥时会自动使用 deterministic fallback。

```powershell
cd D:\Projects\AI-Agent-Interview-Coach
python scripts/evaluate.py
python scripts/evaluate_interview.py
python scripts\evaluate_interview_agent.py --suite all --json-out artifacts\evals\latest.json
python -m unittest
npm run lint:frontend
```

核心验收信号：

- v1/v2/v3/memory 离线评测保持通过。
- `interview_agent` regression/capability/source eval 全部写出可审计结果。
- regression 不允许原始回答泄露、禁用词命中或关键工具链断裂。
- source eval 关注抽取 precision/recall、重复合并和来源质量，而不是只看页面是否抓到。
- 完整发布前使用 `docs/product/release-checklist.md` 走一遍手工验收。

## API 说明

### Phase 1

```text
POST /v1/documents
{ "id": "sop-001", "html": "<html>...</html>" }
→ 201 { "id": "sop-001", "title": "后端服务 On-Call SOP" }

GET /v1/search?q=OOM
→ 200 { "query": "OOM", "results": [...] }
```

典型验收：

- `GET /v1/search?q=OOM` 返回 `sop-001`
- `GET /v1/search?q=故障` 返回多个 SOP
- `GET /v1/search?q=replication` 返回空，因为该词只在 script 中
- `GET /v1/search?q=CDN` 返回 `sop-003` 和 `sop-010`

### Phase 2

```text
GET /v2/search?q=服务器挂了
→ 200 { "query": "服务器挂了", "results": [...] }
```

典型验收：

- `服务器挂了`：后端服务和 SRE SOP 靠前
- `黑客攻击`：安全团队 SOP 靠前
- `机器学习模型出问题`：AI & 算法 SOP 靠前

### Phase 3

```text
GET /v3
GET /v3/questions
GET /v3/sources
GET /v3/review
POST /interview/chat/stream
```

`/v3` 是 AI Agent 岗模拟面试训练模式，`/interview` 保留为同一页面的兼容入口。顶栏功能页：

- `/v3`：面试主流程，只保留当前题目、换题、回答框、流式追问和评分复盘。
- 追问会作为下一轮面试官问题继续当前题，完成追问回答后再进入下一题，避免面试节奏像题库刷题。
- 开始面试会优先读取服务端 `/interview/session-plan`，根据 L3 弱点记忆、最近作答记录和题目频率生成本场题单，避免每次固定抽同一批题。
- `/v3/questions`：题库管理，用于导入本地面经、刷新题库、查看题目和来源分布。
- `/v3/sources`：登录态管理，只展示牛客、小红书、知乎三类平台授权状态；搜索、筛选和入库由后台采集 Agent 复用登录态完成，并以简洁状态展示最近任务、失败原因和最近入库题目。
- `/v3/review`：复盘页，根据已保存的模拟面试历史展示完成题目、平均分和最近追问建议。
- 复盘页优先读取服务端 `/interview/review` 聚合结果，按 `session + question` 合并初答和追问，浏览器本地历史只作为临时兜底。
- 面试结束消息会读取 `/interview/sessions/{session_id}/summary`，给出本场完成题目、平均分、薄弱主题和下一场训练建议。
- 面试结束后会自动追加 `/interview/sessions/{session_id}/report` 生成的 Markdown 报告，用于演示、复盘和沉淀训练记录；报告不暴露原始回答。

面试训练能力：

- 从本地面经 Markdown 导入结构化题库，默认读取 `D:\Plan\.raw\Agent面经融合_小红书+牛客_20260510.md`、`D:\Plan\.raw\牛客_Agent面经_20260510`、`D:\Plan\.raw\小红书_Agent面经_20260509`。
- 支持牛客、小红书、知乎的用户授权登录态管理；真实 cookies/localStorage 保存在本机 Chromium profile，SQLite 只记录 host/profile 元数据。
- 后台采集 job 状态持久化到 SQLite，应用重启后仍可看到最近任务；重启时中断的 running/queued 任务会标记为失败并提示重试。
- 牛客、小红书、知乎各有轻量平台 adapter：后台先抓搜索页，再展开结果详情页；如果搜索页没有可用详情链接，会降级抽取搜索页可见内容。
- 每次采集都会保存 `raw.html`、`extracted.md` 和 `meta.json` 到 `.cache/source_pages/<job_id>/`，用于回放、排查和 source eval。
- job 会记录新增题、重复题、候选块、噪声块、fallback 页数、有效题率和质量标签；前端只展示简洁状态，不暴露搜索 URL 和爬虫参数。
- 入库会过滤常见 UI/广告噪声，并在重复题 metadata 中合并来源 URL、source snapshot、host、extractor 和 collection job id；`frequency` 表示多来源重复出现的热度。
- 流式展示题目、工具调用过程、prompt-driven 面试官反馈、追问和弱点记忆写入。
- 使用 deterministic eval 检查题库抽取、AI 评价区分度、follow-up、weakness memory、tool coverage 和 browser-login 边界。

Agent 编排链：

- `load_question_context`：读取题目 topic、难度、频次、平台和来源快照，避免无上下文评分。
- `analyze_resume_alignment`：把当前题目和已导入简历做轻量关键词对齐，让追问落到候选人真实项目。
- `retrieve_similar_questions`：召回同主题高频相似题，用于下一题规划和横向比较。
- `recall_weakness_memory`：召回 L3 `interview_weakness`，让训练能延续上次薄弱点。
- `grade_answer`：按概念准确性、工程细节、权衡深度、Eval 意识和项目落地评分。
- `direct_interview_turn`：用独立面试官 prompt 结合题目、回答、相似题和弱点记忆，决定追问、反馈和下一步方向；无模型时回退到 deterministic director。
- `update_weakness_memory`：低分时写入长期弱点记忆，高分时显式跳过。
- `persist_interview_turn`：保存本轮问题、回答、评分、追问和建议，支持服务端回放。

相关接口：

```text
POST /interview/sources/import
GET /interview/questions
POST /interview/questions
GET /interview/session-plan
POST /interview/chat/stream
GET /interview/sessions/{session_id}/turns
GET /interview/sessions/{session_id}/summary
GET /interview/sessions/{session_id}/report
GET /interview/review
GET /interview/resume
POST /interview/resume/import-default
POST /interview/resume/upload
GET /interview/web-login
POST /interview/web-login
GET /interview/source-platforms
POST /interview/source-platforms/{platform_id}/open-login
POST /interview/source-platforms/{platform_id}/sync
GET /interview/source-platforms/{platform_id}/jobs/latest
DELETE /interview/source-platforms/{platform_id}
POST /interview/browser/open-login
DELETE /interview/web-login/{host}
POST /interview/sources/import-web
```

授权浏览器登录态：

```powershell
# 安装依赖后会自动启用 Playwright 浏览器连接器；也可以显式打开：
$env:INTERVIEW_ENABLE_BROWSER="1"
# 可选：用本机 Edge/Chrome 通道，更接近真实用户浏览器；不设置时会优先探测本机 Chrome/Edge
$env:INTERVIEW_BROWSER_CHANNEL="msedge"   # 或 chrome
# 可选：默认打开可见窗口；只有自动化 smoke 时才建议设为 1
$env:INTERVIEW_BROWSER_HEADLESS="0"
python app.py
```

使用流程：

1. 在 `/v3/sources` 查看牛客、小红书、知乎三个平台的授权状态、后台采集状态和最近入库题目。
2. 点击某个平台的“打开登录”，在可见浏览器里手动登录、扫码或完成平台验证。
3. 关闭登录窗口后，该平台显示为已授权；后台采集 Agent 会复用同一 host 的本机 profile 搜索并入库相关面经。
4. 点击“断开”会忘记该平台登录态并删除本机 profile 目录。

登录态边界：

- 真实 cookies、localStorage、IndexedDB 等浏览器状态保存在 `.cache/browser_profiles/<host>` 的 Playwright persistent profile。
- SQLite 只保存 host、profile 路径和时间戳，不保存 cookie 明文。
- 这不是绕过风控的裸爬虫；遇到验证码或登录墙时由用户接管，产品语义是“用户授权资料导入”。
- Tauri 桌面版只负责轻量壳和启动 Python sidecar，仍复用这套 Playwright profile，不把第三方登录态绑死在 Tauri WebView 内。

### Phase 4

```text
POST /interview/chat/stream
{ "session_id": "default", "question_id": "...", "answer": "..." }
→ SSE question / tool_call / tool_result / memory / grade / coaching / follow_up / done

GET /interview/sessions/default/turns
→ 200 { "items": [{ "score_total": 7, "answer_preview": "[answer hidden]", "answer_chars": 42, ... }] }

GET /v3/memory
GET /v3/memory/search?q=支付服务
DELETE /v3/memory/{memory_id}
```

记忆边界：

- L0 raw events：保留底层对话事件、工具轨迹和评分过程，用于 provenance。
- L1 atomic memories：显式事实和结构化上下文；同一 dedupe key 的新事实会覆盖旧事实并保留来源链。
- L2 scene memories：用于归纳可复用场景，例如一次失败回答背后的问题类型和修正路径。
- L3 profile / weakness：保存长期画像和面试弱点；面试训练当前主要写入 `interview_weakness`。
- `expires_at`、soft delete 和 active filter 支持过期隐藏与手动删除。
- Memory context 是面试训练上下文，不替代题库来源和 AI 面试官判断。
- 面试原始回答只用于评分和本机 SQLite 持久化；普通复盘、报告和 turns API 默认只返回脱敏占位与长度，不返回 `user_answer` 明文。

评测方法参考 Anthropic 的 Agent eval 思路：优先使用可重复的确定性 grader，同时检查 outcome、tool trace 和 evidence，而不是只看最终自然语言答案。

```powershell
$env:INTERVIEW_SOURCE_PATHS="D:\Plan\.raw\Agent面经融合_小红书+牛客_20260510.md;D:\Plan\.raw\牛客_Agent面经_20260510;D:\Plan\.raw\小红书_Agent面经_20260509"
python scripts/evaluate_interview.py
python scripts\evaluate_interview_agent.py --suite regression
python scripts\evaluate_interview_agent.py --suite capability --trials 3
python scripts\evaluate_interview_agent.py --suite source
```

`interview_agent` eval 分三层：

- `regression`：必须稳定，检查追问关键词、评分区间、禁用词、工具链覆盖和原始回答泄露。
- `capability`：用于爬坡，衡量更难的真实面试表现，不把第一版能力硬凑成满分。
- `source`：固定 HTML fixtures，检查来源抽取 precision/recall 和重复合并。

简历表述：

> 构建 AI Agent 岗模拟面试训练系统，支持本地面经与用户授权网页资料接入、题库结构化抽取、流式追问式面试、AI 评价、弱点长期记忆与离线 Agent Eval；浏览器登录态由本机 Chromium profile 托管，后端仅保存 host/profile 元数据。

## 真实模型配置

项目使用 OpenAI-compatible 协议。不要把真实 API Key 写入仓库。

```powershell
$env:ONCALL_EMBEDDING_BASE_URL="https://api.siliconflow.cn/v1"
$env:ONCALL_EMBEDDING_API_KEY="..."
$env:ONCALL_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"

$env:ONCALL_CHAT_BASE_URL="http://127.0.0.1:8080/v1"
$env:ONCALL_CHAT_API_KEY="..."
$env:ONCALL_CHAT_MODEL="gpt-5.4"
```

也可以使用兼容变量：

```powershell
$env:OPENAI_BASE_URL="http://127.0.0.1:8080/v1"
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-5.4"
```

真实 provider smoke test 是 opt-in：

```powershell
$env:ONCALL_RUN_INTEGRATION="1"
python -m unittest tests.integration.test_real_providers -v
```

## 安全与提交说明

- `.env`、`.cache/`、`.venv/`、`node_modules/`、`docs/`、`output/`、`AGENTS.md` 均不进入最终提交包。
- `.env.example` 是示例配置，可以保留。
