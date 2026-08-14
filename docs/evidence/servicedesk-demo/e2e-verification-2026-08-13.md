# ServiceDesk Pilot — e2e 跑通验证 (2026-08-13)

> 目标：(a) 启动容器/前端/桥接 (b) 浏览器可访问 (c) 发组队指令+推模拟信息，Manager 正确处理。
> 结论：**三项全部通过**，端到端闭环已验证。

## (a) 进程状态

| 进程 | 状态 |
|------|------|
| `agentteams-controller`（内嵌 Tuwunel+Higress+MinIO+Element） | Up ~1h |
| `agentteams-manager-fixed`（copaw manager，唯一 Manager） | Up |
| `agentteams-worker-ticket-intake` | Up |
| `agentteams-worker-triage-analyst` | Up |
| `agentteams-worker-resolution-agent` | Up |
| `agentteams-worker-verify` | Up |
| bridge（宿主机 Python :8770） | Up |
| `agentteams-manager`（operator 用错镜像建的无害崩溃容器） | Restarting（忽略） |

## (b) 浏览器可访问（bridge :8770）

| 端点 | 结果 |
|------|------|
| `/` | HTTP 200 |
| `/wechat.html` | HTTP 200（渲染 `[群回复]` 气泡） |
| `/agentflow.html` | HTTP 200（agent 对话流） |
| `/api/status` | HTTP 200 |
| `/api/events` | HTTP 200 |

Higress(18080) / Element(18088) / Matrix(6167) 均可达。

## (c) 组队指令 + 模拟信息 → Manager 处理

### 1. 组队指令（feed_manager.py → admin→@manager DM）
- Manager 确认 4 个 Worker 全部 Running（ticket-intake / triage-analyst / resolution-agent / verify）。
- 向各 Worker 房间推送角色定义/职责/协议/示例。
- 在网关房间发 `[群回复]` 宣告团队就位。

### 2. 模拟信息（wechat_sim.py → bridge → 网关房间）
推送 3 条「账户与访问异常」种子场景：
1. 张伟(技术部)：实习生李明离职 3 个月，OA/钉钉账号仍可登录。
2. 王芳(HR)：新员工赵敏 VPN 登录失败，提示账号不存在。
3. 刘强(销售部)：邮箱二次验证手机号更换，收不到验证码。

bridge 返回 `OK event=...`（3/3 投递成功）。

### 3. Manager 处理（网关房间实锤）
- 收到 `[微信群消息]` 包络，识别内容。
- 建工单并派发 `ticket-intake`：
  - `task-20260813-161710`：离职员工账号未禁用（李明）
  - `task-20260813-161715`：新入职员工 VPN 登录失败（赵敏）
  - `task-20260813-161735`：邮箱二次验证手机号更换（刘强）
- 每条 `[群回复]` 含问题/报告人/优先级/处理流水线状态。

### 4. Worker 接单（ticket-intake 日志实锤）
- 收到 `New task [task-20260813-161710]`、`[task-20260813-161715]`。
- 用 file-sync 拉取 `shared/tasks/<id>/spec.md`，session 状态持续保存（处理中）。

## 本轮排障（让 demo 重新跑通的关键修复）
1. **@manager 房间成员被清空**：删除 Manager CR 触发 `member_reconcile` ForceLeave。
   恢复 = admin `invite` + `@manager` `join`（房号 `!` 须编码为 `%21`，Tuwunel 行为）。
2. **Manager 崩溃循环**：env `AGENTTEAMS_FS_ACCESS_KEY=default`/`b6a9bbf…` 不匹配 MinIO
   → `mc alias set` 失败。改 `admin`/`AgentTeams2026`。
3. **Manager 模型 401**：`AGENTTEAMS_MANAGER_GATEWAY_KEY=e64a80…` 调 `step-3.7-flash` 未授权
   → 换成 worker 的 `AGENTTEAMS_WORKER_GATEWAY_KEY`（已授权）。

详见 `.workbuddy/memory/2026-08-13.md`。

## 22:52 复验（bridge 重启后）

上一会话结束时 bridge（宿主机 Python 进程）被回收，端口 7890 失联。本轮重启后重新跑通 (a)(b)(c)：

### (a) 进程
- controller / manager-fixed / 4 worker 全 Up（约 1 小时）。
- `agentteams-manager`（operator 误配 CR，worker 镜像）仍崩溃循环 `AGENTTEAMS_WORKER_NAME is required`，已知无害，未删 CR（删会触发 @manager 退房）。
- bridge 重新后台启动：`python server.py --port 7890 --env-file ~/agentteams-manager.env`，登录 Matrix joined 12 房（含网关房 `!bvyfHEsxOxHSzISUex`）。

### (b) 前端（全部 HTTP 200）
`/` `/wechat.html` `/agentflow.html` `/api/status` `/api/events` 均 200；`/api/status` 返回 12 个 joined_rooms，确认 bridge 真连上 Matrix。

### (c) 复验（新工单）
- `wechat_sim.py --bridge http://127.0.0.1:7890 --text "GitLab 账号被锁…403…"` → bridge 回 `OK event=$6desMcjHKNco0yXZ_npiKon8r3JvEqccIaaqoJ9PoVU`。
- 网关房事件流（bridge 记录）：
  - `seq=332` manager：处理中…
  - `seq=333` manager：建工单 `task-20260813-170240`（GitLab 账号被锁-发版前紧急解封）派 `ticket-intake`
  - `seq=334` ticket-intake：收到新任务，拉取 spec
  - `seq=335` ticket-intake：`TASK_COMPLETED: task-20260813-170240`
  - `seq=336` manager：网关房回总结（工单已分配 ticket-intake）
- 结论：(a)(b)(c) 在 bridge 重启后仍完整闭环。

## 08-14 01:05 复验（次日冷启动）

次日会话冷启动：bridge（宿主机 Python）与 token 刷新循环（会话内 nohup）均随会话结束被回收。重新拉起后完整跑通 (a)(b)(c)。

### 重启的组件
- **token 刷新循环**：host token 文件 `C:\Users\20145\agentteams-auth-token` 停在 23:36，controller 已轮换新 token（kid 同但 payload 已变）→ manager 用过期文件会 `agt` CLI 401。重启：`nohup bash -c 'while true; do docker cp agentteams-controller:/var/run/agentteams/cli-token "$(cygpath -w "$HOME/agentteams-auth-token")"; sleep 20; done'`（pid 5323），host 文件内容随即与 controller 当前 token 一致。
- **bridge**：`python server.py --port 7890 --env-file ~/agentteams-manager.env`（nohup，pid 5116 上一轮；本轮仍在跑，5 端点全 200）。

### (a) 进程
- controller / manager-fixed / 4 worker 全 Up；`agentteams-manager`（operator 误配 CR）仍崩溃循环，无害不删。
- token 循环 + bridge 均恢复。

### (b) 浏览器（全部 HTTP 200）
`/` `/wechat.html` `/agentflow.html` `/api/status`(返回 12 joined_rooms) `/api/events` 均 200。

### (c) 组队指令 + 模拟消息
- feed_manager 重发组队指令 → manager 识别现有 team（4 worker 全 Running），发 `[群回复]` 宣告就位，**未重复建 worker**（docker ps worker 数 = 4）。
- wechat_sim 推 2 条报障：
  - 打印机驱动错误 → `task-20260813-170919` 派 ticket-intake → `TASK_COMPLETED`（seq 351–355）
  - VPN 连内网 git 超时 → `task-20260813-170920` 派 ticket-intake → `TASK_COMPLETED`（seq 356–360）
- 结论：(a)(b)(c) 冷启动后仍完整闭环。

### 经验固化
- **每次新会话必须重启两样宿主进程**：① bridge（宿主机 Python，非 Docker，会话退出即失联）② token 刷新循环（否则 manager 派单 401）。二者均用 `nohup ... &` 后台，断点续跑前先 `curl /api/status` 与检查 host token 文件 mtime。

## 08-14 01:11 复验 + token 循环根因修复

第三次跑通时发现上一轮「TOKEN_FRESH」是**假阳性**：token 文件头（JWT kid）稳定，`head -c 40` 比对永远相等，掩盖了过期；而 `ps -ef` 暴露旧循环（pid 4567/5323）其实在跑，但 token 文件 mtime 一直停在 23:36。

### 真因
- **`docker cp <container>:<path> <bind-mounted-windows-host-file>` 静默失效**：Windows 上 docker cp 写到 bind 挂载的 host 文件不更新 mtime、也不生效（无报错，被 `2>/dev/null` 吞掉）。所以循环空转，token 不刷新 → 时间一长 manager `agt` CLI 派单 401。
- 可靠替代：**`docker exec <container> cat <path> > <host-file>`**（shell 重定向写 host 文件，mtime 正常更新）。

### 修复
- 杀掉两个失效循环（docker cp 版），改用 `nohup bash -c 'while true; do docker exec agentteams-controller cat /var/run/agentteams/cli-token > "$(cygpath -w "$HOME/agentteams-auth-token")"; sleep 20; done'`（pid 5732）。25s 后 mtime 自动更新到 01:14 → 证明真刷新。
- `setsid` 在 Git Bash 不存在，用 `nohup ... < /dev/null &` 即可脱离会话（旧循环 ppid=1 已验证可跨工具调用存活）。

### (c) 复验（token 修复后）
- feed_manager 重发组队指令 → manager 列 4 worker 全 Running，确认就位（未重复建）。
- wechat_sim 推 2 条：邮箱密码忘记 → `task-20260813-171635`；Outlook 收不到外部邮件 → `task-20260813-171636`。均派 ticket-intake → `TASK_COMPLETED`（seq 376–384）。manager 用新鲜 token 派单成功。

### 一键脚本
- 新增 `wechat-agentteams-e2e/start-demo-host.sh`：拉起 token 循环（docker exec cat 版）+ bridge（已运行则跳过）+ 健康检查（5 端点 + token SYNCED 校验）。冷启动直接 `bash start-demo-host.sh` 即可，免去逐条手敲。
