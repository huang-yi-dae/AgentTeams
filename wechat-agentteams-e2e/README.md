# wechat-agentteams-e2e · 微信群 → Agent Team → 回传 端到端演示

基于 AgentTeams 原生 Docker 部署，宿主机 Python 模拟「微信群报障」推入体系，容器内 6 个 Agent 协作处理后回传群聊，通过零 mock 双视图实时观测。

> 数据真实性约束：两个 HTML 视图渲染的每一条消息都来自容器内 Matrix 实时 `/sync` 事件，无 mock。

## 环境要求

| 依赖 | 说明 |
|------|------|
| Docker Desktop 4.x+ | WSL2 后端 |
| Python 3.10+ | 纯标准库 |
| Windows 11 24H2 | 需配置 `.wslconfig` 设 `networkingMode=nat` |

## 快速开始

### 1. 部署 AgentTeams

```powershell
$env:AGENTTEAMS_NON_INTERACTIVE="1"
$env:AGENTTEAMS_LLM_PROVIDER="openai-compat"
$env:AGENTTEAMS_OPENAI_BASE_URL="https://api.stepfun.com/step_plan/v1"
$env:AGENTTEAMS_DEFAULT_MODEL="step-3.7-flash"
$env:AGENTTEAMS_LLM_API_KEY="<YOUR_KEY>"
$env:AGENTTEAMS_ADMIN_USER="admin"
$env:AGENTTEAMS_ADMIN_PASSWORD="AgentTeams2026"
$env:AGENTTEAMS_MOUNT_SOCKET="1"
& ".\install\agentteams-install.ps1" manager
```

⚠️ 如果只有 controller 没有 manager：重建时加 `-e AGENTTEAMS_MATRIX_APPSERVICE_ENABLED=false`（见 `_recreate_controller.sh`）。

### 2. 启动桥接

```powershell
cd wechat-agentteams-e2e/bridge
python server.py --port 8770
```

访问: 总览 `8770/`, 视图一 `8770/agentflow.html`, 视图二 `8770/wechat.html`。

### 3. 投喂组队 + 模拟消息

```powershell
python feed_manager.py --wait 150           # 投喂组队指令
cd ../simulator && python wechat_sim.py --interval 60  # 推送模拟消息
```

## 关键文件

| 路径 | 作用 |
|------|------|
| `bridge/matrix_client.py` | Matrix 客户端 (纯标准库) |
| `bridge/server.py` | 桥接服务 + 双视图 |
| `bridge/feed_manager.py` | DM 投喂组队指令 |
| `simulator/wechat_sim.py` | 微信群消息模拟器 |
| `simulator/messages.json` | 6 条种子场景 |
| `viewer/*.html` | 三视图 (零 mock) |
| `prompts/manager-team-prompt.md` | Manager 组队指令 |

## 验证步骤（5 步跑通全链路）

**前置：** 确认 Docker Desktop 已启动且 `docker ps` 显示 `agentteams-controller` 和 `agentteams-manager` 均为 Up。

| 步骤 | 操作 | 验证点 |
|------|------|--------|
| 1 | 启动桥接 `python bridge/server.py --port 8770` | 终端显示 `admin login OK` + 找到 `微信群-IT服务台支持群` |
| 2 | 投喂组队 `python bridge/feed_manager.py --wait 150` | Manager 回复组队完成，`docker ps` 出现 4 个 worker 容器 |
| 3 | 模拟消息 `python simulator/wechat_sim.py --interval 60 --count 3` | 终端显示每条发送 OK |
| 4 | 打开 `http://127.0.0.1:8770/wechat.html` | 群消息 → 服务台回复 完整闭环 |
| 5 | 打开 `http://127.0.0.1:8770/agentflow.html` | Manager 拆解分派 + Worker 执行 真实对话流 |
| 对照 | Element Web `http://127.0.0.1:18088` (admin/AgentTeams2026) | 与自建视图对照，确认零 mock |

## 常见问题

- **端口 18080 000**: 设 `.wslconfig` 为 NAT 模式并重启 Docker
- **AppService panic**: 重建加 `-e AGENTTEAMS_MATRIX_APPSERVICE_ENABLED=false`
- **模型报错**: 确认 `AGENTTEAMS_DEFAULT_MODEL` 为有效模型名
