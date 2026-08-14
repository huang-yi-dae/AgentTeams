# ServiceDesk Pilot E2E — 运行证据

> 本目录存放 `wechat-agentteams-e2e/` 完整 e2e 链路（微信群 → Bridge → Matrix → Manager → 4 Worker）的运行证据。
> 与 `servicedesk-demo/`（纯 Python 降级方案证据）并列存在。
> 上层说明见 [`../../README.md`](../../README.md)、[`../../RUNBOOK.md`](../../RUNBOOK.md)。

## 证据文件清单（当前提交状态）

### 截图证据

| 文件名 | 内容 |
|---|---|
| `viewer-index.png` | Bridge 总览页 `http://127.0.0.1:7890/` |
| `viewer-agentflow.png` | Agent 对话流视图 `http://127.0.0.1:7890/agentflow.html` |
| `viewer-wechat.png` | 模拟微信群视图 `http://127.0.0.1:7890/wechat.html` |
| `element-gateway-room.png` | Element Web 网关房 `微信群-IT服务台支持群` |

### 文本 / 终端证据（替代部分缺失截图）

| 文件名 | 内容 | 生成方式 |
|---|---|---|
| `start-demo-host.txt` | PowerShell 跑 `.\start-demo-host.ps1` 输出（含 `[demo] token: SYNCED`） | 终端输出落盘 |
| `docker-ps.txt` | 6 个 agentteams-* 容器状态 | `docker ps` 输出落盘 |
| `agt-get-workers.txt` | Controller 注册的 4 个 Worker | `agt get workers -o json` 输出落盘 |
| `higress-console-status.txt` | Higress Console 端口可达 + login API 测试结果 | curl 输出落盘 |
| `bridge-summary.txt` | Bridge event store 统计（各 kind / sender 分布 + 最近 Manager 回复） | Python 解析 API 落盘 |

### 容器日志

| 文件名 | 内容 |
|---|---|
| `container-controller.log` | controller 容器最后 200 行 stdout |
| `container-manager.log` | manager 容器最后 200 行 stdout |

### 文档

| 文件名 | 内容 |
|---|---|
| `README.md` | 本文件 |

## 未截图的项目及原因

| 原计划项目 | 状态 | 替代方案 |
|---|---|---|
| `element-manager-dm.png` | 未截图（Element Web 临时断连） | 见 `container-manager.log` 中 Manager 收到 feed_manager.py DM 的记录 |
| `element-worker-room.png` | 未截图 | 见 `agt-get-workers.txt` 中 4 个 Worker 的 roomID |
| `higress-console.png` | **Higress Console SPA UI 加载异常**，登录页无 password input 元素（详见下方说明） | 见 `higress-console-status.txt` 端口可达性 + login API 测试 |
| `bridge.log` | 未截屏（bridge 是隐藏后台进程，无 stdout 落盘路径） | 见 `bridge-summary.txt` 实时 event store 统计 |

## 关于 Higress Console 登录异常

**现象**：浏览器打开 `http://127.0.0.1:18080/`，页面加载但看不到密码框。
**根因**：Higress Console 是 React SPA 应用，HTML 体积仅 2741 字符，登录表单由客户端 JS hydration 后才动态注入。当前环境下 SPA hydration 可能失败（具体原因需进一步排查，可能是 React bundle 静态资源加载问题）。

**绕过方案**：直接使用 Higress Console API（setup-higress.sh 实际使用的方式）：
```bash
curl -s -c cookie.txt -X POST http://127.0.0.1:18080/session/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"AgentTeams2026"}'
```
API 返回 HTTP 201 + Set-Cookie `_hi_sess=...`，证明凭证正确、登录可用。

**已知：未在本次修复范围**。此问题属于 Higress Console 镜像层或 SPA 资源加载问题，不在 ServiceDesk Pilot e2e demo 修复范围内。如需 UI 截图可在后续单独排查（参见 `RUNBOOK.md` §四 controller 已知问题）。

## 复现步骤

```powershell
# 1. 启动 controller
cd D:\Develop\AgentTeams\wechat-agentteams-e2e
.\reset-demo.ps1 -SkipConfirm

# 2. 等就绪 (controller + manager + 4 worker, 约 3 分钟)
Start-Sleep -Seconds 180

# 3. 启动 bridge
cd bridge
python server.py --port 7890 --env-file $env:USERPROFILE\agentteams-manager.env

# 4. 推 6 条场景消息
cd ..\simulator
python wechat_sim.py --bridge http://127.0.0.1:7890 --count 6 --interval 90 `
  --env-file $env:USERPROFILE\agentteams-manager.env `
  --group-room "微信群-IT服务台支持群"

# 5. 等 6 轮全部跑完 (~9 分钟)

# 6. 浏览器截图 4 张 png 放入本目录
```

## 验证 checklist

- [x] `viewer-wechat.png` 显示模拟员工消息 + Manager `[群回复]`（实测有 [OK] 标记的回复）
- [x] `agt-get-workers.txt` 显示 4 个 Worker 全 Running
- [x] `bridge-summary.txt` 含完整事件流：6 轮模拟消息 + Manager 派单链 + 4 Worker 全部活跃
- [x] `container-manager.log` 含 `task-YYYYMMDD-HHMMSS` 派单记录
- [x] `element-gateway-room.png` 显示 Manager 在真实 Matrix 房间中（与 wechat.html 同步）
- [ ] ~~`higress-console.png` 浏览器登录截图~~ — UI 异常，用 API 测试代替