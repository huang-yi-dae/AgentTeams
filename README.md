# ServiceDesk Pilot — 微信群消息驱动的 IT 服务台多 Agent 团队

[![demo](https://img.shields.io/badge/demo-end--to--end--red.svg)](#e-运行证据)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![based on](https://img.shields.io/badge/based%20on-AgentTeams-orange.svg)](https://github.com/agentscope-ai/AgentTeams)

> **ServiceDesk Pilot** 是面向 20~500 人中小企业的 IT 服务台解决方案。它把微信群里的报障消息，自动转化为多 Agent 团队协作处理的工单，最终以口语化回复回传到群里——员工无需下载任何新软件，IT 同事无需介入中转。

本仓库基于 [AgentTeams](https://github.com/agentscope-ai/AgentTeams) 二次开发，所有运行代码、配置样例、运行证据均在仓库内可重现。

---

## 📑 目录

1. [项目背景与场景](#一项目背景与场景)
2. [5 秒跑起来](#二5-秒跑起来)
3. [架构](#三架构)
4. [目录结构](#四目录结构)
5. [(a) 运行入口](#a-运行入口)
6. [(b) 依赖说明](#b-依赖说明)
7. [(c) 配置样例](#c-配置样例)
8. [(d) 输入输出](#d-输入输出)
9. [(e) 运行证据](#e-运行证据)
10. [进阶使用](#五进阶使用)
11. [与官方 AgentTeams 的关系](#六与官方-agentteams-的关系)
12. [致谢与参考](#七致谢与参考)

---

## 一、项目背景与场景

**痛点**：中小企业 IT 通常 1~2 人兼任，员工习惯在微信群里直接报障。常见链路：

```
员工在微信群发消息 → IT 同学肉眼看到 → 凭经验判断 → 手动操作 → 群里回复
```

问题：响应慢、易遗漏、过程无记录、复杂故障跨系统查询耗时。

**ServiceDesk Pilot 的解法**：

```
员工在微信群发消息 ─┐
                   ├─→ Bridge 适配层 ─→ Matrix 房间 ─→ Manager Agent
                   │                                       ├─→ Ticket Intake
IT 同学可继续介入  ─┘                                       ├─→ Triage Analyst
                   ↑                                       ├─→ Resolution
                   │                                       └─→ Verify
                   └──────────── [群回复] ←───────────────────┘
```

服务台 Agent 团队 4 个角色：

| Worker | 职责 |
|---|---|
| **Ticket Intake** | 拆解消息、建工单、抽取实体（人/账号/系统/时间） |
| **Triage Analyst** | 判断类别（账号/网络/设备）、严重度、影响面、决定要不要升级 |
| **Resolution** | 给出可执行修复步骤或具体操作建议 |
| **Verify** | 复核处置是否真正解决、是否需二次确认 |

Manager 收到 `[群回复]` 后回传到群内，员工得到口语化答复。

---

## 二、5 秒跑起来

```bash
# 0. 准备 .env
cd wechat-agentteams-e2e
cp .env.example .env
# 编辑 .env，至少填入 AGENTTEAMS_LLM_API_KEY 与 AGENTTEAMS_ADMIN_PASSWORD

# 1. 启动 controller 容器（约 2 分钟）
./start.sh controller

# 2. 另开一个终端，启动宿主机桥接服务
./start.sh bridge

# 3. 浏览器打开观察页面
./start.sh viewer

# 4. 另开第三个终端，投喂 Manager 组队指令
./start.sh feed

# ⚠️ Windows PowerShell 5.1 用户注意: bridge 重定向用 `> file 2>&1`
#    不要用 `*> file` (这是 PowerShell 7+ 语法, PS 5.1 不支持)

# 5. 推送 6 条模拟微信群消息
./start.sh simulate
```

完整演示流程见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。

---

## 三、架构

```
┌─────────────────────────────────────────────────────────────┐
│                       宿主 机（Windows / WSL）                  │
│                                                              │
│   ┌──────────────────┐    HTTP    ┌───────────────────────┐  │
│   │  Simulator       │ ─────────→ │  Bridge (Python)       │  │
│   │  wechat_sim.py   │   /api/    │  matrix_client.py     │  │
│   │  messages.json   │   send     │  server.py :8770      │  │
│   └──────────────────┘            └─────────┬─────────────┘  │
│                                               │ Matrix C-S    │
│   ┌──────────────────┐    HTTP    ┌──────────▼─────────────┐  │
│   │  Viewer (HTML)   │ ←──────── │  Browser (3 个页面)     │  │
│   │  wechat.html     │   /api/    │  index / agentflow /   │  │
│   │  agentflow.html  │   events   │  wechat                │  │
│   └──────────────────┘            └───────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ Docker 端口映射
                             │ 18080 / 18001 / 18088 / 6167
┌────────────────────────────▼────────────────────────────────┐
│             agentteams-controller 容器 (Docker)                │
│                                                              │
│   ┌────────────┐    ┌────────────┐    ┌──────────────────┐  │
│   │  Tuwunel   │    │  Higress   │    │  Manager Agent   │  │
│   │  Matrix    │◄──►│  Gateway   │◄──►│  ServiceDesk      │  │
│   │  :6167     │    │  :8080     │    │  Pilot            │  │
│   └────────────┘    └────────────┘    └────────┬─────────┘  │
│                              ▲                 │ worker-mgmt │
│                              │                 ▼             │
│                         ┌────┴────┐    ┌──────────────────┐  │
│                         │  MinIO  │    │  Worker Agents    │  │
│                         │  (FS)   │    │  Intake/Triage/   │  │
│                         └─────────┘    │  Resolution/Verify │  │
│                                       └──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**关键设计：Bridge 不实现 Agent 逻辑**——它只是把微信群消息包络转成 Matrix 房间里的标准消息，再把 Manager 回的 `[群回复]` 暴露给浏览器。所有"理解 / 拆解 / 分派"都发生在容器内的 Agent 团队里。

---

## 四、目录结构

```
AgentTeams/                           ← 本仓库根目录
├── README.md                          ← 本文件（比赛提交版）
├── AGENTS.md                          ← AgentTeams 官方导航
├── LICENSE                            ← Apache 2.0
├── wechat-agentteams-e2e/             ← ServiceDesk Pilot 演示入口
│   ├── start.sh                       ← 一键启动入口
│   ├── .env.example                   ← 配置样例
│   ├── _recreate_controller.sh        ← 跨平台容器启动脚本
│   ├── README.md                      ← 本目录内部说明
│   ├── bridge/                        ← 宿主机桥接服务（IM 适配层）
│   │   ├── server.py                  ← HTTP API + Matrix sync
│   │   ├── matrix_client.py           ← Matrix C-S API 客户端
│   │   └── feed_manager.py            ← admin → @manager DM 投喂工具
│   ├── simulator/                     ← 微信群消息模拟器
│   │   ├── wechat_sim.py              ← 推送脚本
│   │   └── messages.json              ← 6 个真实 IT 服务台场景
│   ├── viewer/                        ← 浏览器观察页面（零依赖纯 HTML）
│   │   ├── index.html                 ← 总览
│   │   ├── agentflow.html             ← 视图一：Agent 对话流
│   │   └── wechat.html                ← 视图二：模拟微信群
│   ├── prompts/
│   │   └── manager-team-prompt.md     ← 投喂给 Manager 的系统级组队指令
│   └── presentaion/                       ← 参赛 PPT
├── docs/
│   ├── RUNBOOK.md                     ← 详细运行手册
│   ├── evidence/                      ← 运行证据（截图 + 日志）
│   └── archive/                       ← 原 AgentTeams 官方 README 多语言版本
├── agentteams-controller/             ← Go operator 源码（fork 自官方）
├── manager/  worker/  copaw/  ...    ← AgentTeams 各组件（fork 自官方）
└── plugins/                           ← AgentTeams 官方 plugin 框架
```

---

## 五、比赛提交材料

### (a) 运行入口

**统一入口**：`wechat-agentteams-e2e/start.sh`

| 命令 | 作用 | 推荐演示角色 |
|---|---|---|
| `./start.sh controller` | 启动 agentteams-embedded 容器（含 Matrix、Manager、Workers） | 一次性，约 2 分钟 |
| `./start.sh bridge` | 在宿主机启动 Python 桥接服务（端口 8770） | 常驻进程 |
| `./start.sh viewer` | 打印浏览器观察链接（可自动打开默认浏览器） | 演示时 |
| `./start.sh simulate` | 推送 6 条模拟微信群消息 | 演示时，一次性 |
| `./start.sh feed` | 把 Manager 组队指令投喂到 @manager DM | 演示前一次性 |
| `./start.sh all` | 依次执行上述全部步骤 | 一键全跑 |

**为什么这样组织**：ServiceDesk Pilot 是"容器内 Agent 团队"+"宿主机 IM 适配"双层架构。`start.sh` 把这两层封装成 3 个进程（controller / bridge / simulator），符合 SRE 与演示场景对"分层可控、易排障"的要求。

### (b) 依赖说明

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| **Docker** | Docker Desktop 4.x（Windows/macOS）或 Docker Engine 24+（Linux） | 运行 agentteams-embedded 容器 |
| **Python** | 3.7+ | 运行桥接服务与模拟器（**仅用标准库，零 pip install**） |
| **LLM API Key** | openai-compat 格式（已验证 StepFun step-3.7-flash，可换 Qwen / OpenAI 等） | Manager/Worker 推理 |
| **宿主机资源** | 2 CPU + 4 GB RAM 最低；多 Worker 建议 4 CPU + 8 GB | 容器与 Worker 并发 |

**关键依赖原则**：bridge / simulator / viewer 三个 Python/HTML 组件**不引入任何第三方依赖**。原因：
1. 让评审 clone 仓库即可运行，无需 `pip install`
2. 桥接服务是"薄适配层"，标准库足够
3. 评审容器/沙盒环境通常不能联网装包

### (c) 配置样例

完整配置样例见 [`wechat-agentteams-e2e/.env.example`](wechat-agentteams-e2e/.env.example)。

```bash
# LLM Provider (容器内 Manager / Worker 使用)
AGENTTEAMS_LLM_PROVIDER=openai-compat
AGENTTEAMS_DEFAULT_MODEL=step-3.7-flash
AGENTTEAMS_LLM_API_KEY=<replace-with-your-openai-compat-key>
AGENTTEAMS_OPENAI_BASE_URL=https://api.stepfun.com/step_plan/v1

# Matrix admin (容器与宿主机 bridge 共用)
AGENTTEAMS_ADMIN_USER=admin
AGENTTEAMS_ADMIN_PASSWORD=AgentTeams2026

# 端口与域名
AGENTTEAMS_PORT_GATEWAY=18080
AGENTTEAMS_MATRIX_DOMAIN=matrix-local.agentteams.io:18080

# Runtime & locale
AGENTTEAMS_MANAGER_RUNTIME=copaw
AGENTTEAMS_LANGUAGE=zh
TZ=Asia/Shanghai
```

**首次使用**：

```bash
cd wechat-agentteams-e2e
cp .env.example .env
vi .env   # 填入真实 AGENTTEAMS_LLM_API_KEY
```

`.env` 在 `.gitignore` 中，不会被提交。

**`~/agentteams-manager.env`**：由容器启动后自动生成到用户 home 目录，包含 admin password 与 Matrix 端口。宿主机 bridge 启动时通过 `--env-file` 读取它。

### (d) 输入输出

**输入**：6 个真实 IT 服务台场景（见 [`wechat-agentteams-e2e/simulator/messages.json`](wechat-agentteams-e2e/simulator/messages.json)）

| # | 场景 | 报障人 | 类别 |
|---|---|---|---|
| 1 | 离职员工 OA / 钉钉账号未禁用 | 张号(技术部) | 账号生命周期 |
| 2 | 新员工 VPN 登录失败 | 王芳(HR) | 账号开通 |
| 3 | 二次验证手机号变更 | 刘强(销售部) | MFA |
| 4 | 密码过期无法重置 | 陈丽(财务部) | 密码/邮件 |
| 5 | 内网 GitLab 403 Forbidden | 马超(研发部) | 网络/权限 |
| 6 | 三台新打印机网络配置 | 杨雪(行政部) | 设备（非账户类） |

**包络格式**（Bridge 识别的群消息约定）：

```
[微信群消息] 群: <群名> | 成员: <报障人> | 消息ID: <唯一ID> | 时间: <时间戳>
内容: <原始报障文本>
```

**处理流程**：

```
微信群 ──包络──> Bridge ──> Matrix 房间 ──> Manager
                                              ├─ Ticket Intake 拆解实体，建 ticket_id
                                              ├─ Triage Analyst 判定类别/严重度
                                              ├─ Resolution 给具体修复步骤
                                              └─ Verify 复核
                                          <─ [群回复] 汇总
微信群 <─包络── Bridge <── "群回复" <──── Manager
```

**输出**：

- **视图一 Agent 对话流**：实时显示 Manager/Worker 之间的对话（来自 Matrix 真实事件）
- **视图二 模拟微信群**：以微信 UI 风格还原员工报障 → 服务台回复
- **bridge stdout 日志**：每个事件的序列号、时间戳、发送者、事件 ID

### (e) 运行证据

证据存放于 [`docs/evidence/`](docs/evidence/)：

| 文件 | 内容 |
|---|---|
| `bridge.log` | 宿主机桥接服务的完整 stdout（含 6 轮"收消息 → 拆解 → 派发 → 回复"日志） |
| `viewer-index.png` | 总览页面截图 |
| `viewer-agentflow.png` | Agent 对话流页面截图 |
| `viewer-wechat.png` | 模拟微信群页面截图 |
| `container-logs.txt` | `docker logs agentteams-controller` 末尾 200 行 |

**复现步骤**（评审可独立验证）：

```bash
# 1. 启动 demo
cd wechat-agentteams-e2e
./start.sh controller
./start.sh bridge &
./start.sh feed
./start.sh simulate

# 2. 打开浏览器，访问 http://127.0.0.1:8770/

# 3. 留证
# - 终端 1: ./start.sh bridge > ../docs/evidence/bridge.log 2>&1
# - 浏览器截图保存到 docs/evidence/viewer-*.png
# - 终端 2: docker logs agentteams-controller > ../docs/evidence/container-logs.txt
```

---

## 五、进阶使用

### 端口占用参考

| 端口 | 用途 |
|---|---|
| 8770 | 宿主机 Bridge HTTP API + Viewer |
| 18080 | 容器内 Higress Console |
| 18001 | 容器内辅助 |
| 18088 | 容器内辅助 |
| 6167 | 容器内 Matrix 客户端端口（给 Bridge 直连用） |

### 投递自定义消息

```bash
# 投递一条临时消息
python3 wechat-agentteams-e2e/simulator/wechat_sim.py \
  --bridge http://127.0.0.1:8770 \
  --text "VPN 连不上，提示证书过期" \
  --sender "测试员工"
```

### 切换 LLM Provider

修改 `.env` 中的 `AGENTTEAMS_LLM_API_KEY` 与 `AGENTTEAMS_OPENAI_BASE_URL`，重启 controller 即可。已验证兼容 StepFun、Qwen、OpenAI 等 openai-compat 接口。

---

## 六、与官方 AgentTeams 的关系

本仓库 fork 自 [agentscope-ai/AgentTeams](https://github.com/agentscope-ai/AgentTeams)。我们对官方代码做了**最小侵入式二次开发**：

| 模块 | 改动 | 性质 |
|---|---|---|
| `wechat-agentteams-e2e/` | **新增** | ServiceDesk Pilot 演示入口 |
| `wechat-agentteams-e2e/_recreate_controller.sh` | **新增 / 重写** | 跨平台容器启动脚本 |
| `README.md` | **重写** | 官方 README 面向 K8s 部署；本 README 面向"比赛提交"维度 |
| `README.zh-CN.md` / `README.ja-JP.md` | **归档到 `docs/archive/`** | 保留作为官方版本参考 |
| `agentteams-controller/` `manager/` `worker/` `copaw/` `hermes/` `openclaw-base/` `openhuman/` `helm/` `qwenpaw/` `plugins/` | **未改动** | 直接使用官方版本运行 |

**未引入新组件原则**：ServiceDesk Pilot 复用 AgentTeams 原生的 Manager + 4 Worker 模型，没有新增 operator、新增镜像、新增运行时。仅在 IM 接入层做了适配，把"模拟微信群"作为新的 IM 信源接进 Matrix 房间。

**Manager 提示词的二次开发**：见 [`wechat-agentteams-e2e/prompts/manager-team-prompt.md`](wechat-agentteams-e2e/prompts/manager-team-prompt.md)——它定义了 ServiceDesk Pilot 的协议：
- 消息包络识别规则
- 4 个 Worker 的职责边界
- 自动推进规则（避免每阶段都要人工确认）
- 唯一例外：不可逆操作前必须发确认消息

---

## 七、致谢与参考

- **AgentTeams 官方仓库**：[github.com/agentscope-ai/AgentTeams](https://github.com/agentscope-ai/AgentTeams)
- **Higress AI Gateway**：[higress.cn](https://higress.cn/)
- **Tuwunel Matrix Server**：[github.com/matrix-construct/tuwunel](https://github.com/matrix-construct/tuwunel)
- **CoPaw / QwenPaw** — Python-based Agent runtime

---

## License

本项目以 Apache 2.0 协议开源（继承自上游 AgentTeams）。

ServiceDesk Pilot 演示代码（`wechat-agentteams-e2e/`）由本仓库作者贡献。
