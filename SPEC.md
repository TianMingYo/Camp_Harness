# FeedbackLoop Harness 设计规约

**版本：** 0.1（brainstorming 已确认）  
**日期：** 2026-08-08  
**项目类型：** AI4SE A 路 Coding Agent Harness

## 1. 问题陈述

自然语言需求通常不够精确，编码智能体可能修改错误文件、忽略测试反馈、无限重试，或执行超出用户授权范围的命令。本项目构建一个本机运行的 Coding Agent Harness：用户选择已有 Git 仓库并输入一个小功能需求，Harness 组织 LLM 决策、受限工具执行和确定性验收，让失败结果可以结构化回灌给 LLM，直到任务成功或安全暂停。

目标用户是希望让编码智能体完成小型功能、但仍要掌握代码变更范围、测试证据和危险动作审批的软件工程师。项目价值不在于包装一个现成 agent runner，而在于用自己的代码实现一个可测试、可审计的反馈闭环。

## 2. 目标与非目标

### 目标

- 支持本机 Git 仓库和自然语言小功能需求。
- 自动检测测试、lint、类型检查命令，并允许用户覆盖。
- 用户批准计划后，在仓库作用域内自动实施普通读写和验收命令。
- 对危险动作、越权路径、网络和 Git 推送执行确定性拦截并请求 HITL 审批。
- 将退出码和工具结果分类为结构化反馈，驱动下一轮 LLM 修正。
- 提供最多 5 轮、连续无进展暂停等可解释停止策略。
- 用 mock/stub LLM 离线验证所有核心机制，并提供可重复机制演示。
- 提供本机完整 WebUI 和不需要真实 key 的公网 mock 演示 WebUI。

### 非目标

- 不实现通用软件项目管理或多人协作平台。
- 不直接使用 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex Agent 或供应商 agent runner。
- 不允许公网实例访问访问者的本机文件系统。
- 不追求一次性完成大型跨模块需求；单次任务限定为可在有限轮次内验证的小功能。

## 3. 用户故事

1. 作为开发者，我想输入仓库路径和自然语言需求，以便得到一份可审阅的实现计划。
2. 作为开发者，我想看到自动检测出的测试/lint/类型命令并覆盖它们，以便用项目真实标准验收功能。
3. 作为开发者，我想在批准计划后让 Harness 自动完成仓库内普通修改，以便减少重复操作。
4. 作为开发者，我想在危险命令或越权路径出现时收到审批请求，以便保留对高风险动作的控制。
5. 作为开发者，我想看到测试失败被分类并回灌给下一轮 LLM，以便确认 agent 是依据证据修正而不是盲目重试。
6. 作为开发者，我想在达到 5 轮或连续无进展时自动暂停，以便及时接管不明确的任务。
7. 作为评审者，我想在没有真实 LLM 和网络的情况下运行机制演示，以便验证护栏和反馈闭环确实是代码实现。

## 4. 功能规约

### 4.1 任务创建与仓库扫描

- 输入：绝对或相对 Git 仓库路径、自然语言需求、可选验收命令覆盖、可选最大轮数。
- 行为：规范化路径，确认 Git 工作区，读取分支和工作区摘要，识别 `package.json`、`pyproject.toml`、`Cargo.toml` 等项目入口。
- 输出：任务 ID、仓库根目录、当前分支、工作区状态、检测到的命令和风险提示。
- 边界：路径不存在、不是 Git 工作区、路径包含无法访问的链接时拒绝创建。
- 错误处理：返回可操作错误，不启动 LLM，不产生文件修改。

### 4.2 验收命令检测与覆盖

- 输入：扫描结果和用户覆盖项。
- 行为：按项目类型生成测试、lint、类型检查候选；覆盖项完全替换同类候选，并显示最终执行列表。
- 输出：确定性的 `ValidationCommand` 列表，每条包含命令、参数、类别、超时和是否允许自动执行。
- 边界：没有检测到命令时要求用户显式提供至少一条验收命令。
- 错误处理：命令不存在或配置无效在执行前报告，不把它误判为代码失败。

### 4.3 计划生成与确认

- 输入：需求、仓库摘要、项目约定和验收命令。
- 行为：LLM 只能返回结构化计划；Harness 校验文件范围、动作类型和验收标准。
- 输出：修改文件列表、任务步骤、预期行为、验收命令、潜在危险动作和预计轮数。
- 边界：结构化输出解析失败或计划包含仓库外文件时拒绝计划。
- 错误处理：保留原始模型响应的脱敏摘要，提示用户重新生成或手动取消。

### 4.4 动作解析、治理与执行

- 输入：经用户批准的计划和每轮 LLM 动作。
- 行为：解析动作；策略引擎检查路径、命令、网络、删除和 Git 发布；安全动作自动执行，高风险动作进入 HITL。
- 输出：动作结果、退出码、文件变化摘要、审批记录和审计事件。
- 边界：每个写操作必须位于仓库根目录下；命令使用参数数组，不拼接不可信 shell 字符串。
- 错误处理：策略阻断不会执行动作；超时终止子进程并生成 `TIMEOUT` 反馈。

### 4.5 反馈分类与回灌

- 输入：工具结果、退出码、测试报告、工作区快照摘要。
- 行为：使用确定性规则生成 `PASS`、`TEST_FAILURE`、`BUILD_OR_TYPE_FAILURE`、`LINT_FAILURE`、`COMMAND_ERROR`、`POLICY_BLOCKED`、`NO_PROGRESS` 或 `TIMEOUT`。
- 输出：结构化 `Feedback` 和供下一轮使用的短摘要；原始日志单独脱敏存储。
- 边界：连续两轮等价结果视为无进展；日志超过上限时截断但保留分类依据。
- 错误处理：报告解析失败时保守归类为 `COMMAND_ERROR`，不宣称成功。

### 4.6 停止策略

- 所有验收命令通过且没有策略违规时成功结束。
- 默认最多 5 轮，任务级配置可覆盖但必须有上限。
- 连续两轮 `NO_PROGRESS` 时暂停。
- `POLICY_BLOCKED` 和待审批危险动作暂停在 `awaiting_action_approval`。
- 暂停时保留工作区和完整审计记录，用户可以调整授权或继续。

### 4.7 凭据管理

- 首次使用通过隐藏输入录入 key，供应商、base URL 和模型可更新。
- key 使用操作系统 keyring；数据库只保存元数据和不可逆状态指纹。
- 查看只显示“已配置/未配置”和非敏感指纹，更新和清除可操作。
- 日志、错误、终端输出和 Git 内容经过 token/key 脱敏。

## 5. 非功能性需求

### 性能

- 不涉及 LLM 调用、文件扫描或测试执行的短 UI/API 请求，在参考开发环境中以 p95 1 秒作为基线目标；这不是跨部署环境的硬性验收门槛。
- LLM 调用、仓库扫描、补丁应用和测试执行必须异步化，并通过任务状态和进度事件反馈，不阻塞 Web 请求。
- README 和机制演示记录实际部署环境、测试样本和测量结果；不同 CPU、磁盘、网络和容器资源下以实测结果解释性能。
- 每轮命令有默认超时和可配置上限；日志和反馈摘要有大小上限。
- 上下文按最近轮次和相关文件摘要构建，不随历史无限增长。

### 安全

- 默认仓库作用域隔离，拒绝路径逃逸、危险命令和未经批准的网络。
- LLM 无直接文件或 shell 权限；所有动作经过动作模型和策略引擎。
- key 不进源码、Git、SQLite 明文、日志或终端历史。
- 公网演示只使用内置示例仓库、临时目录和 mock LLM。

### 可用性与可观测性

- WebUI 始终显示当前状态、轮次、剩余轮数、反馈类别和审批原因。
- 每次状态变化、人工决定和停止原因进入审计事件。
- 失败必须能定位到命令、退出码、文件变化和分类规则。

## 6. 系统架构与数据流

```text
WebUI / REST API
        |
Task State Machine ---- SQLite / Audit Log
        |
Context Builder ---- LLM Adapter ---- OpenAI-compatible API or Mock LLM
        |
Action Parser -> Policy Engine -> HITL Approval
        |                         |
        +------ Tool Executor <---+
                    |
       Validation Detector / Command Runner
                    |
             Feedback Classifier
                    |
             next iteration or stop
```

组件职责边界：Web 层不执行命令；LLM Adapter 不执行动作；Policy Engine 不依赖模型判断；Tool Executor 不决定任务是否成功；Feedback Classifier 只处理客观执行结果；State Machine 统一决定继续、成功或暂停。

## 7. 数据模型

- `Task(id, repo_root, request, branch, validation_commands, max_iterations, state, created_at)`
- `Plan(task_id, summary, files, steps, acceptance_criteria, approved_at)`
- `Iteration(id, task_id, number, action_summary, workspace_fingerprint, result_code, feedback_type, progressed, started_at, ended_at)`
- `Action(id, iteration_id, type, path_or_command, risk, status, result_summary)`
- `Approval(id, action_id, reason, decision, decided_at)`
- `Feedback(id, iteration_id, type, exit_code, summary, raw_log_ref)`
- `ProviderConfig(name, base_url, model, key_status, updated_at)`
- `AuditEvent(id, task_id, kind, payload_redacted, created_at)`

关键约束：任务只能引用一个规范化仓库根目录；Iteration 按任务和轮次唯一；Approval 决定不可覆盖；ProviderConfig 不含明文 key；原始日志引用必须指向脱敏内容。

## 8. 领域与机制设计（Coding Agent Harness）

### 动作与工具

最低工具包括文件读取、补丁写入、目录扫描、验收命令执行和工作区快照。工具返回结构化结果，LLM 不能直接调用 Python subprocess。

### 客观反馈

测试退出码、lint/类型检查报告、文件快照差异和命令超时是确定性传感器。Feedback Classifier 将它们映射为有限枚举，供 State Machine 和下一轮上下文使用。

### 危险动作

Policy Engine 对路径逃逸、删除、网络、Git 发布、敏感文件读取和未声明命令执行阻断并请求 HITL。该机制由代码测试，不依赖提示词中“请注意安全”。

### 记忆与上下文

SQLite 保存项目约定、计划、反馈摘要和人工决定；Context Builder 只检索当前任务相关的最近记录和文件摘要，限制上下文预算。

### 主要贡献：反馈闭环

重点实现失败分类、反馈压缩、无进展检测、多轮自我修正和停止状态机。该重点能在 mock LLM 下完全复现，并通过独立单元测试证明。

## 9. 技术选型与分发

- Python 3.12：文件系统、子进程和测试生态成熟，适合自研循环。
- FastAPI + Uvicorn：提供本机 REST/WebUI 和公网演示服务。
- Pydantic：定义并校验结构化动作、反馈和状态数据。
- `httpx`：实现 OpenAI-compatible 单轮 API 调用。
- `keyring`：接入操作系统凭据存储。
- SQLite（标准库）：保存任务和审计数据，减少运行依赖。
- pytest：单元、集成和 mock LLM 测试。
- Docker：构建公网 mock 演示镜像；本机模式提供包安装和启动命令。

WebUI 采用简洁的操作台布局，优先状态可见性、审批可解释性和日志扫描效率。用户在 brainstorming 阶段选择不启用视觉伴侣，因此不生成额外视觉稿；UI 设计会在实现时记录可访问性和信息层级约束。

## 10. 测试与机制演示

机制演示必须离线、可重复，固定复现：mock LLM 首轮写入会导致测试失败的实现；测试传感器返回失败；分类器生成结构化反馈；mock LLM 根据反馈返回修正动作；第二轮通过；另一路动作触发危险命令护栏并等待审批。测试不访问网络、不依赖真实 API key。

一键测试命令、临时 Git 仓库集成测试、WebUI API 测试和公网演示 smoke test 均纳入 CI。

## 11. 分发与运行

本机完整模式提供 Python 包安装命令和本地 WebUI 启动命令，要求 Python 3.12 和 Git。README 必须说明仓库路径授权、keyring 配置、自动检测/覆盖验收命令、平台限制和故障排查。

公网模式通过 Docker 发布，只提供内置 mock 场景，公开 URL 不接受真实 key、不执行访问者任意 shell、不接触本机路径。

## 12. 验收标准

1. 用户可通过 WebUI 创建任务、查看扫描结果并覆盖验收命令。
2. 未批准计划不能写文件或执行验收命令。
3. 计划批准后，普通仓库内动作可自动执行，危险动作必须停在审批状态。
4. mock LLM 场景能稳定展示一次失败回灌和下一轮修正通过。
5. 所有反馈类别、无进展和 5 轮上限都有确定性测试。
6. 任何仓库外路径、敏感文件和未授权网络动作均被拒绝或审批。
7. key 可录入、更新、清除和查看状态，明文永不进入日志或数据库。
8. 本机模式和公网 mock 模式共享同一 harness 核心。
9. CI 有名为 `unit-test` 的 job，且最终执行为 pass。
10. 交付包含 README、Dockerfile、SPEC、PLAN、SPEC_PROCESS、AGENT_LOG、REFLECTION、CI 配置和可访问 WebUI URL。

## 13. 风险与未决问题

- Git 工作区目前尚未初始化为有效仓库；实现前需由 using-git-worktrees 处理仓库和分支策略。
- 课程文档同时提到 GitHub Actions 和必须存在的 `.gitlab-ci.yml`；本项目按最终交付清单优先使用 GitLab CI，并在实现计划中确认目标托管平台。
- 自动检测验收命令可能遇到项目自定义脚本；必须允许用户覆盖并在执行前显示最终列表。
- 不同 OpenAI-compatible 供应商的结构化输出能力不同；Adapter 需要统一错误处理并限制模型响应格式。
- 本机执行任意项目测试仍可能有副作用；命令白名单、超时、资源限制和审批边界需要在实现中进一步验证。
