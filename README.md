# Feedback Loop Harness

一个由项目代码拥有控制权的 Coding Agent Harness。它把自然语言小功能拆成计划，要求人工批准计划，然后按“上下文 → OpenAI-compatible LLM → 结构化动作 → 确定性策略 → 工具执行 → 验证 → 反馈”循环推进。LLM 只提出动作，不能直接获得文件或 shell 权限。

## Installation

需要 Python 3.12+、Git，以及操作系统可用的 keyring backend。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest -q
```

## Local WebUI

```powershell
python -m uvicorn feedbackloop.api:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。本地模式接受一个规范化 Git 仓库路径，自动检测 Python、Node、Rust 验收命令，并允许用 executable 与 JSON 字符串参数数组覆盖。填写 provider、base URL、model，保存同名 provider 的 key，创建任务并确认计划后，长任务由 API background task 启动，WebUI 轮询任务状态。危险动作会显示 Allow/Deny，允许后执行并从下一迭代继续。

## Provider configuration

供应商需要兼容 `POST {base_url}/chat/completions`、Bearer 鉴权和标准 `choices[0].message.content`。运行时配置 provider、base URL 与 model；key 通过 WebUI/API 写入操作系统 keyring，SQLite 只保存配置状态和不可逆指纹。

```http
POST /providers/glm/credentials
Content-Type: application/json

{"key":"<hidden>"}
```

响应只包含 `configured` 和指纹，不回显 key。当前适配器固定请求 JSON object 格式，因此供应商还必须支持 `response_format={"type":"json_object"}`。

## Safety limits

- 所有文件路径在 canonical Git root 内解析，拒绝父目录、绝对路径和符号链接逃逸。
- 敏感文件访问与路径逃逸为 `DENY`；删除、网络、Git push、shell 链接和未声明命令需要 HITL。
- 默认最多 5 轮；连续两轮相同工作区指纹和等价反馈进入 `PAUSED_NO_PROGRESS`。
- 验证命令使用参数数组与 `shell=False`，带超时和输出截断。
- 日志、反馈、audit payload 在 SQLite 前脱敏；真实 key 不进入 Git、日志或数据库。

## Offline demo

离线演示不访问网络，也不读取本机仓库或 key。它固定复现第一轮失败、反馈驱动修正、第二轮通过，以及危险删除需要审批。

```powershell
python -m demo.scenario
```

预期 JSON 中 `corrected_after_feedback` 和 `policy_blocked` 均为 `true`，`used_network` 为 `false`。

## Distribution

```powershell
docker build -t feedbackloop-demo .
docker run --rm -p 8000:8000 feedbackloop-demo
```

容器启动 `feedbackloop.api:demo_app`，只暴露内置 mock demo，不接受宿主机仓库路径或真实 key。GitLab CI 的 `unit-test` job 安装包、执行完整 pytest 和离线 demo。

## Project structure

- `src/feedbackloop/`: 状态机、策略、验证、反馈、provider、存储、凭据、循环、API 和 WebUI。
- `tests/`: unit、integration 与 demo 机制测试。
- `demo/`: 可重复离线场景。
- `SPEC.md` / `PLAN.md`: 已批准规格和 TDD 实现计划。
- `SPEC_PROCESS.md` / `AGENT_LOG.md`: Superpowers 过程、人工决定和偏离记录。

## Known limits

- Windows 无符号链接权限时，相应边界测试会 skip；Linux CI 应执行该测试。
- CommandRunner 截断返回内容，但当前仍由 `communicate()` 暂存完整子进程输出。
- 公网部署 URL 尚未配置；提交前必须完成 GitLab CI pass 和公开 WebUI 部署并在此处补充 URL。
- `REFLECTION.md` 必须由学生本人完成，仓库仅提供问题模板。
- 本地执行器支持仓库内读、写、已批准删除和已声明验收命令；network、Git push 与未声明命令仍会被策略拦截，当前版本不执行这些动作。
- 本地创建任务时必须填写 provider、base URL、model、至少一条验收命令和明确的计划文件路径；应用不会把未列入计划的文件摘要发送给模型。

## Third-party dependencies

FastAPI、Uvicorn、Pydantic、httpx、keyring 与 pytest；许可证以各项目发布包为准。本项目没有复制第三方源代码。
