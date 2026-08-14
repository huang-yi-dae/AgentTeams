# ServiceDesk Pilot — 运行手册（RUNBOOK）

> 本文档是 [`README.md`](../README.md) 的展开版。README 给评审看"是什么 / 怎么跑"，RUNBOOK 给上手的工程师看"怎么排错 / 怎么定制"。

---

## 一、环境准备

### 1.1 操作系统

| OS | 推荐度 | 备注 |
|---|---|---|
| **Windows 11 + WSL2** | ⭐⭐⭐⭐⭐ | 本仓库作者主要使用。Docker Desktop 已集成 WSL2 后端。 |
| macOS 13+ (Apple Silicon) | ⭐⭐⭐⭐ | Docker Desktop for Mac。 |
| Ubuntu 22.04+ / Debian 12 | ⭐⭐⭐⭐ | 原生 Docker Engine。 |
| 纯 Windows (无 WSL) | ⭐⭐⭐ | 可用，但所有 shell 命令需走 PowerShell 或 Git Bash。 |

### 1.2 Docker

- **Windows/macOS**：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，确保 `docker` 命令在 PowerShell / Terminal 中可用。
- **Linux**：`sudo apt install docker.io docker-compose-v2`，把当前用户加入 `docker` 组。

验证：

```bash
docker --version        # 期望: Docker version 24+
docker ps                # 期望: 无错误输出（容器列表可能为空）
```

### 1.3 Python

- **版本**：3.7 及以上（项目用了 type hint 与 f-string，3.6 也基本能跑但建议 3.7+）
- **依赖**：**仅用标准库**。无需 `pip install`。

验证：

```bash
python3 --version        # 期望: Python 3.7+
```

### 1.4 LLM API Key

需要一个 **openai-compat 格式**的 API Key。已验证兼容：

- **StepFun**（推荐，国内访问友好）：`https://api.stepfun.com/step_plan/v1`
- **Qwen / DashScope**：国际版 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- **OpenAI**：`https://api.openai.com/v1`

---

## 二、首次启动

### 2.1 克隆仓库

```bash
git clone <repo-url>
cd AgentTeams
```

### 2.2 准备 .env

```bash
cd wechat-agentteams-e2e
cp .env.example .env
vi .env
```

最少需要改两个值：

```bash
AGENTTEAMS_LLM_API_KEY=<你的真实 key>
AGENTTEAMS_ADMIN_PASSWORD=<任意强密码，建议默认即可>
```

### 2.3 启动 controller

```bash
./start.sh controller
```

预期：

- 脚本提示 `[detect] OS: linux`
- 删除旧容器（如果有），启动新容器 `agentteams-controller`
- 等待约 120 秒让 Manager / Worker 完成 bootstrap
- 容器就绪标志：`~/agentteams-manager.env` 被生成

**故障排查**：

```bash
# 查看容器日志
docker logs -f agentteams-controller

# 常见问题
# 1) 镜像拉取慢 → 配置 Docker 镜像加速 (daemon.json)
# 2) 端口被占用 → 检查 18080/18001/18088/6167
# 3) Docker socket 挂不上 → WSL2 用户检查 docker-desktop 集成已勾选
```

### 2.4 启动 bridge（宿主机）

新开一个终端：

```bash
cd wechat-agentteams-e2e
./start.sh bridge
```

预期：

- 登录 admin 到 Matrix（输出 `admin login OK`）
- 创建/加入网关房间 "微信群-IT服务台支持群"
- 监听端口 8770
- 浏览器可访问 http://127.0.0.1:8770/

### 2.5 投喂 Manager 组队指令

新开第三个终端：

```bash
cd wechat-agentteams-e2e
./start.sh feed
```

预期：

- 把 `prompts/manager-team-prompt.md` 内容发到 admin ↔ @manager 的 DM 房间
- Manager 收到后开始按提示词创建 Worker 团队

### 2.6 打开浏览器观察

```bash
./start.sh viewer
```

预期：自动打开浏览器到 `http://127.0.0.1:8770/`，可见三个入口：

| 页面 | 用途 |
|---|---|
| `/` | 总览 |
| `/agentflow.html` | 视图一：Agent 对话流 |
| `/wechat.html` | 视图二：模拟微信群 |

### 2.7 推送模拟消息

```bash
./start.sh simulate
```

默认按 `messages.json` 顺序推送，间隔 90 秒。脚本只调用 `--count` 控制条数，`--interval` 控制间隔：

```bash
# 推 2 条，间隔 5 秒（演示用）
python3 simulator/wechat_sim.py --bridge http://127.0.0.1:8770 --count 2 --interval 5

# 推一条临时消息
python3 simulator/wechat_sim.py --bridge http://127.0.0.1:8770 --text "VPN 连不上" --sender "测试员工"
```

---

## 三、跑通检查清单

跑通后建议逐项勾选，作为"运行证据"留底：

- [ ] `docker ps | grep agentteams-controller` 显示容器运行中
- [ ] `docker logs agentteams-controller | tail -50` 无 ERROR 关键字
- [ ] `cat ~/agentteams-manager.env` 内容包含 admin password 与 Matrix 端口
- [ ] `curl http://127.0.0.1:8770/api/status` 返回 JSON
- [ ] `curl http://127.0.0.1:18080/` 返回 Higress Console 页面
- [ ] 浏览器打开 `/agentflow.html`，能看到 Manager / Worker 房间已有对话
- [ ] 浏览器打开 `/wechat.html`，能看到已就绪的服务台头像
- [ ] 推送一条测试消息后，`/agentflow.html` 出现新事件
- [ ] Manager 在群里发 `[群回复]`，`/wechat.html` 出现该回复
- [ ] bridge 终端日志保留为 `docs/evidence/bridge.log`

---

## 四、常见问题（FAQ）

### Q1: `./start.sh controller` 报"无法访问 /var/run/docker.sock"

**原因**：Docker Desktop 与 WSL2 集成未开启。

**解决**：
1. Docker Desktop → Settings → Resources → WSL Integration
2. 勾选你使用的发行版（默认 Ubuntu）
3. 重启 Docker Desktop

### Q2: Manager 不响应 / 一直 Waiting

**原因 1**：LLM API Key 无效或网络不通。
- 解决：`docker logs agentteams-controller | grep -i "llm\|model"` 看错误

**原因 2**：Manager 还未完成 bootstrap。
- 解决：等待更长（首次约 120~180s），观察容器日志

**原因 3**：管理员密码不一致。
- 解决：确认 `~/.env` 与 `~/agentteams-manager.env` 的 `AGENTTEAMS_ADMIN_PASSWORD` 一致

### Q3: Bridge 报 "agentteams-manager.env 不存在"

**原因**：controller 容器还在启动中。

**解决**：

```bash
# 强制等待
docker logs -f agentteams-controller
# 等到看到 "Manager is ready" 类似的行
```

### Q4: 端口 8770 被占用

**解决**：修改 `start.sh` 顶部的 `BRIDGE_PORT=8770` 为其他端口（如 17770）。

### Q5: 想换 LLM 模型

修改 `.env` 中 `AGENTTEAMS_DEFAULT_MODEL` 与 `AGENTTEAMS_OPENAI_BASE_URL`，重启 controller。

### Q6: 想跑自己的场景消息

编辑 `simulator/messages.json`，按相同格式新增 `{group, sender, text, scenario}` 四元组。

### Q7: 想看真实的 Matrix 房间

访问 http://127.0.0.1:18080/（Higress Console），用 admin / 你的密码登录，可看到 Matrix 房间全貌。

---

## 五、清理

```bash
# 停掉 controller 容器
docker rm -f agentteams-controller

# 清理 Manager 工作目录（下次启动会重新生成）
rm -rf ~/agentteams-manager
rm ~/agentteams-manager.env
```

---

## 六、进阶定制

### 6.1 自定义 Manager 提示词

编辑 `prompts/manager-team-prompt.md`，然后重新跑 `./start.sh feed` 即可。

### 6.2 替换 Bridge 为其他 IM 信源

`bridge/server.py` 是关键文件。`matrix_client.py` 提供了纯标准库的 Matrix Client-Server 客户端；要接入钉钉、飞书等其他 IM，只需替换"消息入站"那一段，包络协议保持不变即可。

### 6.3 接入真实微信群

需要：iPad/PC 协议 hook（WeChatFerry 等），将群消息转发到本 bridge 的 `/api/send`。包络格式不变。

---

## 七、性能与并发参考

| 配置 | 期望 | 实测 |
|---|---|---|
| 单 Worker 处理单工单 | < 60s（含 4 个 LLM 调用） | 视模型而定 |
| 6 个工单串行处理 | < 8 分钟 | 推荐演示用 90s 间隔 |
| 6 个工单并行（默认 Manager 行为） | < 2 分钟 | Manager 会自动并行派发 |

---

## 八、参考链接

- [根 README](../README.md)
- [AgentTeams 官方文档](https://github.com/agentscope-ai/AgentTeams)
- [Matrix Client-Server API 规范](https://spec.matrix.org/v1.11/client-server-api/)
- [Higress 文档](https://higress.cn/)

### Q8: controller 启动后 bridge/feed 报 `HTTP Error 503: Service Unavailable`

**原因**：Tuwunel Matrix server 启动失败。`docker logs agentteams-controller` 会看到：
```
ERROR tuwunel_core::config::check: Registration token was specified but is empty ("")
```

**修复**：在 `.env` 里加一行：
```
AGENTTEAMS_REGISTRATION_TOKEN=dev-token-2026
```

然后 `./start.ps1 controller` 重启。

**为什么 `.env.example` 现在默认就有这个值**：Tuwunel 的 `start-tuwunel.sh` 有这一行：
```bash
export CONDUWUIT_REGISTRATION_TOKEN="${AGENTTEAMS_REGISTRATION_TOKEN}"
```
如果 env var 未设置，会变成空字符串，Tuwunel 判定配置错误直接退出。

### Q9: bridge 命令用 `*> file` 重定向没反应

**原因**：PowerShell 5.1 不支持 `*>` 语法（这是 PowerShell 7+ 的）。PS 5.1 会把它当成普通 redirect，报"目录名称无效"。

**修复**：用 PS 5.1 兼容写法：
```powershell
.\start.ps1 bridge > ..\docs\evidence\bridge.log 2>&1
```


### Q10: controller 容器跑着但 Manager / Worker 容器没起来

**症状**：`agt get managers` / `agt get workers` 显示 PHASE = `Pending`，但 `docker ps` 只有 controller 容器。

**原因**：controller operator 找不到 docker backend。`tail -f /var/log/agentteams/agentteams-controller-error.log` 会看到：
```
"no worker backend available, manager needs manual start"
```

**根因**：`_recreate_controller.sh` / `start.ps1 controller` 没把宿主机的 docker socket 挂进 controller 容器。controller operator 启动时检测不到 socket，就认为没有 docker backend。

**修复**：在 controller 容器启动命令里加上 `-v "/var/run/docker.sock:/var/run/docker.sock"`（最新版本的 `start.ps1` 已经默认带这个挂载）。


### Q11: Manager 容器在循环 Restarting，controller 报 "higress init: connection refused"

**症状**：
```
"error":"restore manager gateway auth: ensure consumer: ensure consumer manager: higress init: Post \"http://127.0.0.1:8001/system/init\": dial tcp 127.0.0.1:8001: connect: connection refused"
```

**根因**：`.env` 里缺 `AGENTTEAMS_AI_GATEWAY_ADMIN_URL`。controller 二进制硬编码默认值为 `http://127.0.0.1:8001`，manager 容器用这个错的 URL 连不上 higress，K8s 重启 manager。

**修复**：在 `.env` 追加：
```
AGENTTEAMS_AI_GATEWAY_ADMIN_URL=http://agentteams-controller:8001
```

然后 `docker restart agentteams-controller`。

### Q12: Agent 容器 env 里的 "127.0.0.1" 错在哪里统一替换

Agent 镜像里的 `openclaw.json` 默认有：
- `matrix.homeserver = "http://127.0.0.1:6167"` ❌（应该是 `http://agentteams-controller:6167`）
- `groups.*.requireMention = true` ❌（会导致 manager 不响应没 @ 它的群消息）

**修复**：container 起来后立即 sed：
```bash
docker exec agentteams-manager sed -i 's|"http://127.0.0.1:6167"|"http://agentteams-controller:6167"|g; s|"requireMention": true|"requireMention": false|g' /root/manager-workspace/openclaw.json
docker exec agentteams-worker-ticket-intake sed -i 's|"http://127.0.0.1:6167"|"http://agentteams-controller:6167"|g; s|"requireMention": true|"requireMention": false|g' /root/.copaw-worker/ticket-intake/openclaw.json
# 同样修其他 3 个 worker
```


### Q13: Manager 收不到 `[微信群消息]`, 群里静默忽略

**症状**：群里发了微信群消息包络，Manager 不派单、在群里回复 "继续静默忽略 / 微信联系人尚未被批准"。

**根因**：Manager 默认按 `channel-management` skill 把 Matrix 群消息 sender 当作身份。但 ServiceDesk Pilot 的桥接架构里 sender 永远是 admin（admin 账号代理转发），真正的报障人在包络 `成员:` 字段里。

**修复**：本场景已通过 `wechat-agentteams-e2e/prompts/manager-team-prompt.md` 第一章 "sender / 身份规则覆盖" 解决。reset 后 Manager 启动会读新 prompt。

### Q14: Manager 派了 ticket-intake 后没继续派 triage/resolution/verify

**症状**：state.json 显示 `active_tasks: [{assigned_to: ticket-intake}]`，但 triage-analyst / resolution / verify 从未收到任务，Manager 直接在群里回复 "工单已创建"。

**根因**：LLM 倾向于简化流程，看到 ticket-intake 派出后立刻回群，跳过后续 Worker。

**修复**：已通过 `manager-team-prompt.md` 第六章 "强制派单规则" 第 4 条 "派单链必须完整跑完（顺序强约束）" 解决。规则为：
```
ticket-intake → triage-analyst → resolution → verify
每一步必须等当前 Worker 的 TASK_COMPLETED 回报到达后，才能派下一个
不允许在派单链没跑完时就在群里回 [群回复]
```

### Q15: Manager 的 `[群回复]` 消息没出现在 wechat.html / 带 `*` 前缀

**症状**：Manager 回了群，但 wechat.html 看不到；或者回复内容以 `* [群回复]` 开头。

**根因 1**：LLM 加了 markdown 修饰（如 `*` 斜体），破坏 `[群回复] ` 前缀字节级约束。
**根因 2**：旧版本 Bridge 只匹配 `body.startswith("[群回复]")`，前缀不严格就漏识别。

**修复（双保险）**：
1. `manager-team-prompt.md` 第一章 "字节级约束" + 5 个错误示例 + 1 个正确示例
2. `bridge/server.py` 兜底分支：`role == "manager" and room_label == 网关房` → 自动标 `wechat_reply`，不依赖前缀

### Q16: reset-demo.ps1 跑到一半 docker 命令全部 500 失败

**症状**：所有 `docker exec / docker logs` 返回 `request returned 500 Internal Server Error for API route and version .../dockerDesktopLinuxEngine/...`。

**根因**：Docker Desktop 引擎在 controller 重启过程中 API 路由短暂失败，PowerShell 不抛异常（只是非零 exit），导致后续步骤看似在跑实则无效。

**修复**：`reset-demo.ps1` Step 0 预检 `docker info + docker version`，失败立刻退出并提示重启 Docker Desktop。

### Q17: Higress Console (http://127.0.0.1:18080/) 登录页看不到密码框

**症状**：浏览器打开 Higress Console 后页面有 username 输入框但没有 password 输入框，无法登录。

**根因**：Higress Console 是 React SPA 应用，HTML body 仅 ~2741 字符，登录表单由客户端 JS hydration 后才动态注入。当前环境下 SPA hydration 可能失败（属 Higress 镜像层 / SPA 资源加载问题）。

**绕过**：直接用 API 登录（也是 `setup-higress.sh` 实际使用的方式）：
```bash
curl -s -c cookie.txt -X POST http://127.0.0.1:18080/session/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"AgentTeams2026"}'
# 返回 HTTP 201 + Set-Cookie _hi_sess=..., 凭证正确
```

**未在本次修复范围**：此问题属 Higress Console 镜像 / SPA 资源加载问题，不在 ServiceDesk Pilot e2e 范围。


---

## 三、降级方案：纯 Python Demo（推荐用于比赛演示）

> **背景**：`agentteams-embedded:latest` 镜像里的 controller operator 有多个严重 bug（见 §四 已知问题），无法跑通 manager/worker 容器闭环。已用**纯 Python 标准库 demo** 作为降级方案，跑通 9 阶段端到端闭环。

### 3.1 跑通步骤

```bash
cd servicedesk-pilot-demo
python run_demo.py --approval-mode auto_skip   # 跑全部 5 个场景
```

### 3.2 跑通后的产物

| 产物 | 路径 | 用途 |
|---|---|---|
| `out/dashboard.html` | HTML 亮色主题看板 | 评审视觉展示 |
| `out/report.md` | 文字版复盘报告 | 评审文字阅读 |
| `out/trace.json` | 全链路 Trace | 评审审计 |

5 个场景示例输出：
```
指标:工单 5 · 解决 3 · 升级 2 · 免审批 1 · 知识写回 13
知识库:runbooks 4→5 · cases 4→9 · badcases 0→1
MCP 工具调用:7 / 86%
RAG 命中率:5 / 80%
```

### 3.3 产物已留证于 `docs/evidence/servicedesk-demo/`

- `dashboard.html` (34KB)
- `report.md` (4KB)
- `trace.json` (222KB)

---

## 四、已知问题:agentteams-embedded controller operator bug

`agentteams-embedded:latest` 镜像里的 controller operator (Go) 存在以下无法通过配置绕开的 bug:

### 4.1 manager 镜像名缺失
controller 二进制里 hardcode 了 worker 镜像名 (`agentteams-copaw-worker:latest`),**没有 manager 镜像名**。fallback 用 worker 镜像创建 manager 容器,导致 manager 跑 worker 进程(缺 `AGENTTEAMS_WORKER_NAME` 报错)。

### 4.2 agent 容器 env IP 错误
agent 容器 env 中 `AGENTTEAMS_AI_GATEWAY_URL` / `MATRIX_URL` 都是 `127.0.0.1`,但每个 agent 容器独立 loopback 没有这些服务。manager/worker 无法连 controller 的 Higress / Matrix。

### 4.3 FS env 漏传
controller 创建 worker 容器时漏传 `AGENTTEAMS_FS_ENDPOINT`,worker 启动报 `AGENTTEAMS_FS_ENDPOINT is required`。

### 4.4 Token refresh 卡死
agent 容器 dead 后 controller 还在调 `docker exec create` 而不是 `docker run` 重建容器。

### 4.5 MANAGER_GATEWAY_KEY 未生成
higress API 调用失败导致 manager 凭证生成流程中断,manager 容器启动报 `AGENTTEAMS_MANAGER_GATEWAY_KEY is required`。

**修复方向**:PR 给上游 `agentscope-ai/AgentTeams`。

**当前绕过（2026-08-14 更新）**:
- **本地直接跑通 `wechat-agentteams-e2e/`**:本机有补丁版镜像 `agentteams/agentteams-embedded:fixed`（创建于 2026-08-10），已把正确配置烘焙进镜像——`AGENTTEAMS_MATRIX_URL=http://127.0.0.1:6167`、`AGENTTEAMS_ADMIN_PASSWORD=AgentTeams2026`（与 matrix 实际密码一致）、`AGENTTEAMS_MANAGER_RUNTIME=copaw` + `AGENTTEAMS_MANAGER_IMAGE=higress-registry.cn-hangzhou.cr.aliyuncs.com/agentteams/agentteams-manager-copaw:latest`（带完整 registry 前缀）、`AGENTTEAMS_FS_ENDPOINT` / `AGENTTEAMS_MANAGER_GATEWAY_KEY` 全齐。用它替换上游 `:latest` 即可规避 §4.1–4.5 全部 bug，`wechat-agentteams-e2e/` 完整链路（controller → bridge → Manager 组队 → 工单闭环）可直接跑通。该镜像由 `start.ps1` / `reset-demo.ps1` 默认使用。
  - ⚠️ `copaw` 是**合法**的 Manager runtime（与 worker 共用 copaw-manager 镜像），并非 worker-only；之前"Manager 必须用 openclaw/qwenpaw"的判断已证伪。
  - ⚠️ `:fixed` 是**本地 tag, 不在公开 registry**; 评委/外部按 `:latest` 复现仍会撞上述 bug。
- **对外可复现降级方案**:`servicedesk-pilot-demo/` 纯 Python 演示, 保留 `wechat-agentteams-e2e/` 代码作为未来工作基础。

---

## 五、wechat-agentteams-e2e 完整代码已就绪（待 controller 修复后跑通）

`wechat-agentteams-e2e/` 是完整的"微信群 → Bridge → Matrix → Manager → Worker"链路实现,包含:

| 文件 | 行数 | 作用 |
|---|---|---|
| `start.ps1` | 340 | PowerShell 一键启动入口(6 子命令) |
| `start.sh` | 247 | Bash 跨平台启动入口 |
| `.env.example` | 30 | 配置样例(含 `AGENTTEAMS_AI_GATEWAY_ADMIN_URL`、`AGENTTEAMS_REGISTRATION_TOKEN` 等) |
| `_recreate_controller.sh` | 115 | 跨平台容器启动脚本 |
| `bridge/server.py` | 200+ | HTTP API + Matrix sync |
| `bridge/matrix_client.py` | 100+ | Matrix C-S API 客户端(标准库实现) |
| `bridge/feed_manager.py` | 80+ | admin → @manager DM 投喂 |
| `simulator/wechat_sim.py` | 80+ | 微信群消息模拟器 |
| `viewer/*.html` | 3 个 | 浏览器可视化(总览/Agent 流/微信群) |
| `prompts/manager-team-prompt.md` | 80 | ServiceDesk Pilot 协议(消息包络/4 Worker 职责/自动推进规则) |

**架构**:3 进程(controller Docker / bridge 宿主机 Python / simulator 宿主机 Python)。

**待修复的 controller bug 后**,按 RUNBOOK §二 步骤跑通即可。
