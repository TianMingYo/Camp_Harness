# SPEC 生成过程记录

## 过程范围

本文件记录 Superpowers `brainstorming` 阶段如何从课程要求收敛到
`SPEC.md`。当前没有写入任何实现代码；所有选择都先经过用户确认。

## 关键迭代

### 迭代 1：选择主要贡献维度

- AI 提问：反馈闭环、治理/HITL、记忆/上下文、工具与编排中选择一个主角。
- 用户决策：选择“反馈闭环”。
- 影响：将失败分类、反馈压缩、多轮修正、无进展检测和停止状态机定义为主要贡献；其余五个维度提供最低可运行实现。
- 原因：反馈可由退出码、测试报告和工作区快照确定性验证，最符合 A 路“机制必须是代码”和 mock LLM 测试要求。

### 迭代 2：限定真实使用场景

- AI 提问：优先修复失败测试、实现小功能、修复构建/lint，还是做通用任务。
- 用户决策：根据自然语言需求实现小功能。
- 影响：计划阶段必须从自然语言需求产出拟修改文件和验收标准；反馈闭环用项目测试/lint/类型检查判断功能是否完成。
- 修正：没有把产品收窄成单一“测试修复器”，但通过最多 5 轮和小功能边界控制范围。

### 迭代 3：仓库访问方式与验收命令

- AI 提问：本机仓库路径、Git URL、ZIP 上传或全部支持。
- 用户决策：本机仓库路径。
- AI 提问：验收命令自动检测、每次手填，还是只读项目配置。
- 用户决策：自动检测 + 用户可覆盖。
- 影响：产品定位为本机完整模式；需要路径作用域、符号链接逃逸检查、项目类型探测和最终命令确认页面。

### 迭代 4：授权模型

- AI 提议：计划确认后仓库内自主执行，危险动作单独审批。
- 用户决策：接受。
- 关键澄清：LLM 不直接拥有 shell/文件权限；用户不需要批准每次普通写入，Harness 根据已批准计划和确定性策略执行。
- 影响：新增 `Policy Engine`、`Approval` 状态和危险动作审计；普通仓库内写入不进入逐文件 HITL。

### 迭代 5：LLM 与公网边界

- 用户决策：使用 OpenAI-compatible API，允许配置任意兼容供应商。
- AI 提议：本地完整 WebUI + 公网 mock 演示站。
- 用户决策：接受。
- 影响：真实 key 只服务本机模式；公网只挂载内置示例仓库和 mock LLM，两个模式共享自研核心。

### 迭代 6：停止策略

- AI 提议：默认最多 5 轮、连续两轮无进展暂停、危险动作立即暂停。
- 用户决策：接受。
- 影响：`NO_PROGRESS` 必须由工作区快照和反馈等价性确定；State Machine 需要可恢复暂停状态。

### 迭代 7：技术方案与界面

- AI 提出 Python 模块化核心 + FastAPI WebUI、TypeScript/React、Go 单文件服务三种方案。
- 用户决策：确认 Python + FastAPI 方案。
- 用户拒绝视觉伴侣，因此 UI 采用文字规约和实现阶段的可访问性检查，不生成额外视觉稿。

### 迭代 8：性能指标修订

- 人工反馈：本地 UI 操作不应被固定的 500ms 门槛约束；本机、公网和容器部署环境差异很大。
- 采纳修改：将 500ms 硬门槛改为参考开发环境中短请求 p95 1 秒的基线目标；长任务统一异步化，通过状态和进度事件反馈，并要求 README 记录实际部署测量结果。
- 未改变部分：反馈闭环的轮次、测试证据和安全停止条件仍是功能验收标准，不受该性能指标调整影响。

## 人工判断与未决项

- 人工确认主要贡献为反馈闭环，而不是照搬 Superpowers 的 agent loop。
- 人工确认公网演示不能访问本机仓库或真实 key。
- Git 元数据当前无效；实现前必须按 `using-git-worktrees` 规则处理仓库状态。
- 课程文档对 GitHub Actions 与 `.gitlab-ci.yml` 的要求存在冲突，留到计划/交付平台确认时处理，并记录任何偏离。

## Cold-start validation (2026-08-08)

- **Required context:** a different supported coding-agent type received only `SPEC.md` and `PLAN.md` and was instructed to attempt Tasks 1-2 with TDD.
- **Gemini CLI 0.39.0:** both the default `gemini-3.1-pro-preview` model and explicit `gemini-2.5-flash` model exhausted ten retries with `503 model_not_found`.
- **Claude Code 2.1.118:** after locating the existing portable Git Bash, the CLI exited with `API Error: Unable to connect to API (ConnectionRefused)`.
- **Pause point:** neither agent reached the specification, so there are no independent interface interpretations or ambiguities to apply.
- **Decision:** NO-GO. Per PLAN Task 0, implementation is paused for a human choice of an available supported second agent/provider or an explicit documented deviation.

### Cold-start follow-up (2026-08-10)

- **Second agent:** Claude Code 2.1.118 using the human-configured GLM 5.2 provider.
- **Result:** the second CLI was available and completed an isolated Task 1-2 attempt using only the approved documents. It found no missing basic sample assertions, but could not run Python tests because unattended execution required approval.
- **Document revisions:** the state machine now has an explicit internal `validation_passed` gate; `Workspace.resolve_repo()` requires a `.git` marker; `Action` includes command/network/Git-push proposals; sensitive-file denial precedes deletion approval; policy tests use temporary Git markers.
- **Decision:** GO for specification review after the revisions. The generated cold-start source remains excluded from implementation; its missing runtime test evidence is a logged environment deviation, and primary task implementers must provide actual RED/GREEN runs.
