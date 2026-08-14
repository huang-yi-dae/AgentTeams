# wechat-agentteams-e2e — ServiceDesk Pilot 演示入口

> 本目录是 ServiceDesk Pilot 比赛演示的全部代码。从这里开始上手最快。
> 上层说明见 [根 README](../README.md) 与 [运行手册](../docs/RUNBOOK.md)。

## 一键启动 (PowerShell, 推荐)

> 本 demo 在 Windows 上以 PowerShell 为主路径（bridge / token 循环 / 重置均为 `.ps1`）。
> 首次准备 `.env` 后，直接跑 `reset-demo.ps1` 即可完成「重建容器 → 拉 bridge → 组队 → 打开浏览器」全流程。

```powershell
cd D:\Develop\AgentTeams\wechat-agentteams-e2e
Copy-Item .env.example .env     # 1. 准备配置, 编辑填入 AGENTTEAMS_LLM_API_KEY
.\reset-demo.ps1 -SkipConfirm   # 2. 一键重建并跑通 (约 3~4 分钟, 含 feed 组队)
# 跑完后浏览器自动弹出; 推测试消息:
cd simulator
python wechat_sim.py --bridge http://127.0.0.1:7890 --text "公司打印机连上但打印乱码" --sender "王Printer"
```

分步版 (PowerShell)：

```powershell
.\start.ps1 controller        # 步骤 1: 启动 agentteams-embedded:fixed 容器 (Docker)
.\start-demo-host.ps1         # 步骤 2: 拉起 bridge(7890) + token 循环 + 健康检查 (另开终端)
.\start.ps1 feed             # 步骤 3: 投喂 Manager 组队指令
.\start.ps1 viewer           # 步骤 4: 浏览器打开观察
.\start.ps1 simulate         # 步骤 5: 推送 6 条模拟消息
```

> Bash 备用入口为 `start.sh` (跨平台), 但其 `BRIDGE_PORT` 默认值 8770 已过时, 实际 bridge 端口是 **7890**, 如需用 bash 路径请自行修正端口。

## 本目录结构

```
wechat-agentteams-e2e/
├── start.ps1                  一键启动入口 (PowerShell, controller/bridge/viewer/simulate/feed)
├── start.sh                   一键启动入口 (Bash 跨平台, 端口默认值 8770 已过时, 请用 PS 版)
├── .env.example               配置样例
├── .gitignore                 排除 .env 与日志
├── _recreate_controller.sh    跨平台 controller 容器启动脚本 (bash)
├── reset-demo.ps1             彻底重置: 删容器+volume → 重建 → bridge → feed → 开浏览器
├── start-demo-host.ps1        宿主进程拉起: token 循环 + bridge(7890) + 健康检查
├── enable-yolo.ps1            在 manager 容器写入 /root/manager-workspace/yolo-mode (跳过审批)
├── README.md                  本文件（对内说明）
│
├── bridge/                    宿主机 IM 适配层 (核心混合层 / bridge)
│   ├── server.py              HTTP API + Matrix sync 主服务 (端口 7890)
│   ├── matrix_client.py       Matrix C-S API 客户端 (标准库实现, 连 6167)
│   └── feed_manager.py        admin → @manager DM 投喂工具
│
├── simulator/                 微信群消息模拟器
│   ├── wechat_sim.py          推送脚本 (按 JSON 顺序推送或临时单条, 默认 --bridge :7890)
│   └── messages.json          6 个真实 IT 服务台场景
│
├── viewer/                    浏览器观察页面 (零依赖纯 HTML)
│   ├── index.html             总览
│   ├── agentflow.html         视图一: Agent 对话流 (来自 Matrix 真实事件)
│   └── wechat.html            视图二: 模拟微信群 (员工 ↔ 服务台, 含「清屏」按钮)
│
├── prompts/
│   └── manager-team-prompt.md 投喂给 Manager 的系统级组队指令
│
└── presentaion/                   参赛 PPT (V2.1 ~ V2.3 迭代)
```

## 三个进程的角色

| 进程 | 在哪跑 | 端口 | 作用 |
|---|---|---|---|
| **controller** | Docker 容器 | 18080 / 18001 / 18088 / 6167 | Matrix / Higress / Manager / 4 个 Worker |
| **bridge** | 宿主机 Python | 7890 | IM 适配层 (模拟微信群 ↔ Matrix 房间 ↔ 浏览器) |
| **simulator** | 宿主机 Python (一次性) | — | 推送模拟微信群消息 |

## 冷启动 / 反复验证 (宿主进程)

> controller 容器是 Docker 常驻; 但 **bridge (端口 7890) 与 token 刷新循环是宿主机进程**, 重启电脑 / 关闭终端后会失联, 需要重新拉起。下面脚本专门干这个。

### 一键拉起 (PowerShell, 推荐)

```powershell
cd D:\Develop\AgentTeams\wechat-agentteams-e2e
.\start-demo-host.ps1            # 默认 env=~\agentteams-manager.env, port=7890
# 或指定参数:
.\start-demo-host.ps1 -EnvFile ~\agentteams-manager.env -Port 7890
```

脚本会: ① 杀掉旧 token 循环并以 `docker exec cat` 重新拉起 (每 20s 刷新, 跨 token 轮换存活) ② 端口空闲则拉起 bridge, 已在跑则跳过 ③ 打印 5 个端点 HTTP 码 + `token: SYNCED` 校验。

### 手动分步 (PowerShell)

```powershell
# 1) 杀掉旧 bridge (端口 7890)
Get-NetTCPConnection -LocalPort 7890 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# 2) 重新启动 bridge (加载最新 server.py 修复)
cd D:\Develop\AgentTeams\wechat-agentteams-e2e\bridge
Start-Process python -ArgumentList @('server.py','--port','7890','--env-file',"$env:USERPROFILE\agentteams-manager.env") -WindowStyle Hidden

# 3) 确认 5 个端点都 200
foreach ($p in @('/','/wechat.html','/agentflow.html','/api/status','/api/events')) {
  $code = (Invoke-WebRequest ("http://localhost:7890"+$p) -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue).StatusCode
  Write-Host ($p + ' -> ' + $code)
}

# 4) 组队指令 (manager 确认 4 worker 就位)
cd D:\Develop\AgentTeams\wechat-agentteams-e2e\bridge
python feed_manager.py --env-file $env:USERPROFILE\agentteams-manager.env --wait 90

# 5) 推模拟消息 (--text / --sender 可任意改)
cd D:\Develop\AgentTeams\wechat-agentteams-e2e\simulator
python wechat_sim.py --bridge http://127.0.0.1:7890 --text "我的邮箱密码忘了,自助重置提示账号异常" --sender "陈晨"
python wechat_sim.py --bridge http://127.0.0.1:7890 --text "会议室预定系统登不进去,单点登录跳转报错" --sender "孙明"

# 6) 看 manager 处理事件 (事件流)
cd D:\Develop\AgentTeams\wechat-agentteams-e2e\simulator
python -c "import json,urllib.request,time; b='http://127.0.0.1:7890'
def ev(s): return json.loads(urllib.request.urlopen(b+'/api/events?since='+str(s),timeout=30).read())
l=ev(0); s=l[-1]['seq']
import sys
for i in range(8):
    time.sleep(9); e=ev(s)
    [print(f\"seq={x['seq']} [{x.get('kind')}] {x.get('sender_local')}: {x.get('body','')[:90]}\") for x in e]
    s=max((x['seq'] for x in e), default=s)"
```

### 浏览器观察

- Agent 对话流: `http://127.0.0.1:7890/`
- 模拟微信群视图: `http://127.0.0.1:7890/wechat.html` (若历史消息显示 `undefined`, 是旧 bridge 未加载修复; 重跑 `.\start-demo-host.ps1` 强制重启 bridge 即可, 新消息正常显示)
- Element 登录: `http://127.0.0.1:18088`

#### Element 登录前必须配置 hosts

`matrix-local.agentteams.io` 必须解析到本机, 否则 Element 会报"家服务器链接不是有效的 Matrix 家服务器"或 502。

**以管理员身份打开 PowerShell, 执行:**

```powershell
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "`n127.0.0.1 matrix-local.agentteams.io`n" -Encoding UTF8
# 验证
ping -n 1 matrix-local.agentteams.io
```

看到 `来自 127.0.0.1 的回复` 即生效。

#### Element 登录信息

| 项 | 值 |
|---|---|
| Element 地址 | `http://127.0.0.1:18088` |
| 选择服务器 | **其他自定义服务器** |
| Homeserver URL | `http://matrix-local.agentteams.io:18080` (必须带 `:18080`) |
| 用户名 | `@admin:matrix-local.agentteams.io:18080` 或只填 `admin` |
| 密码 | `AgentTeams2026` (来自 `~/agentteams-manager.env` 的 `AGENTTEAMS_ADMIN_PASSWORD`) |

> 若 Element 仍坚持走 HTTPS, 可换成 homeserver URL `http://127.0.0.1:18080`。

## 如何确认整体跑通

跑通的标准 = controller + bridge + Manager 组队 + 工单完整生命周期 全部正常。

| # | 检查项 | 通过标志 |
|---|---|---|
| 1 | `http://127.0.0.1:7890/` 总览页 | 浏览器能打开, 5 个端点都 200 |
| 2 | `http://127.0.0.1:7890/wechat.html` | 能看到「清屏」按钮, 无 `undefined` |
| 3 | Manager 组队 | feed 后 Manager 回复「...已就位」或类似确认 |
| 4 | 发送一条测试消息 | `wechat.html` 显示该条消息内容正确 |
| 5 | Manager 创建工单 | `agentflow.html` 出现 `已创建IT服务台工单 task-xxxxxxxx` |
| 6 | 工单被分配 | 同页出现 `工单已分配给 ticket-intake` |
| 7 | 工单推进完成 | 后续出现 `TASK_COMPLETED` / 处理摘要 / 实体提取 |
| 8 | token 同步 | `start-demo-host.ps1` 输出 `[demo] token: SYNCED` |

> 只要第 5~7 步完整出现, 即证明 ServiceDesk Pilot e2e 跑通。

### Manager 卡在 "Waiting for approval" 怎么办

`reset-demo.ps1` 与 `start-demo-host.ps1` 都会**自动调用 `enable-yolo.ps1`** —— 在 manager 容器 `/root/manager-workspace/yolo-mode` 写一个空 marker 文件, 让 Manager 下次启动时走 YOLO 模式（admin 不可达时不再等审批, 自己决策不阻塞）。

**手动启用**:

```powershell
cd D:\Develop\AgentTeams\wechat-agentteams-e2e
.\enable-yolo.ps1
```

脚本会:

- manager 容器在跑 → `docker exec agentteams-manager touch /root/manager-workspace/yolo-mode`
- manager 容器没起 → 写到 host 的 `~/agentteams-manager/yolo-mode`, 下次 reset 时容器自动看到

**关键边界**: marker 只在 manager **下一次启动**生效; **当前已经卡在审批的 manager 进程**不会因为新文件自动恢复。处理方法: 在 Element Web 里 manager DM 房间发任意一条消息（例如 "继续"）唤醒它 —— Manager 重新执行 turn 时就不会再走 Tool Guard 拦截路径了。

**关闭 YOLO**:

```powershell
docker exec agentteams-manager rm -f /root/manager-workspace/yolo-mode
# 或下次 reset 前:
Remove-Item -Force ~\agentteams-manager\yolo-mode
```

## 清屏与重置

### 只清前端页面 (保留历史工单)

打开 `http://127.0.0.1:7890/wechat.html`, 点击顶部 **清屏** 按钮, 会立即清空当前页面显示的事件。
这**不会**删除 Matrix 服务器里的历史消息和历史工单, 只是让浏览器视图变干净。

### 彻底重置 (删除所有历史工单与消息)

> ⚠️ 危险操作: 会删除 Docker volume `agentteams-data` 和本机 `~/agentteams-manager`, 所有历史工单/房间/状态都会消失。

```powershell
cd D:\Develop\AgentTeams\wechat-agentteams-e2e
.\reset-demo.ps1
# 脚本会要求输入 yes 确认
```

`reset-demo.ps1` 会按顺序完成:
1. 停止 bridge 与 token 刷新循环
2. 删除 controller 容器
3. 删除 Docker volume `agentteams-data`
4. 删除本机 `~/agentteams-manager` 和 `~/agentteams-auth-token`
5. 重新 `./start.ps1 controller` (约 120s)
6. 重新 `./start-demo-host.ps1`
7. 重新 `feed_manager.py --wait 90`
8. 自动打开浏览器

重置后环境完全干净, 可以直接推送测试消息观察完整流程。

## 设计取舍

- **bridge 用 Python 标准库**: 评审 clone 即可跑, 无需 `pip install`。
- **viewer 用纯 HTML**: 不需要 Node 打包链, 浏览器直接打开。
- **controller 用本地补丁镜像 `agentteams-embedded:fixed`**: 上游 `:latest` 的 controller operator 有多个 bug (RUNBOOK §四: manager 镜像名缺失→崩 `AGENTTEAMS_WORKER_NAME`、生成的 admin 密码与 matrix 实际不一致→login 403、漏传 FS_ENDPOINT / MANAGER_GATEWAY_KEY)。本地 `:fixed` 把这些正确配置烘焙进镜像, 规避上述 bug, 让 `wechat-agentteams-e2e` 完整链路直接跑通。**注意: `:fixed` 是本地 tag, 不在公开 registry; 外部评委按 `:latest` 复现仍会撞上述 bug (属于上游问题, 降级方案见根 README 的纯 Python demo)。**
- **Matrix CS API 在 6167, 不是 18080**: 18080 是 Higress 控制台。`bridge/matrix_client.py` 硬编码连 6167, 不读 env 里指向 Higress 的 `AGENTTEAMS_PORT_GATEWAY`。
- **Manager 提示词即协议**: `prompts/manager-team-prompt.md` 是 ServiceDesk Pilot 的"业务 spec", 把消息包络、4 Worker 职责、自动推进规则写死。
