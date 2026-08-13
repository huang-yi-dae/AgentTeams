# wechat-agentteams-e2e — ServiceDesk Pilot 演示入口

> 本目录是 ServiceDesk Pilot 比赛演示的全部代码。从这里开始上手最快。
> 上层说明见 [根 README](../README.md) 与 [运行手册](../docs/RUNBOOK.md)。

## 一键启动

```bash
cp .env.example .env          # 1. 准备配置
vi .env                        # 2. 填入 AGENTTEAMS_LLM_API_KEY
./start.sh controller          # 3. 启动 controller 容器
./start.sh bridge              # 4. 启动宿主机桥接 (另开终端)
./start.sh feed                # 5. 投喂 Manager 组队指令
./start.sh viewer              # 6. 浏览器打开观察
./start.sh simulate            # 7. 推送 6 条模拟消息
```

## 本目录结构

```
wechat-agentteams-e2e/
├── start.sh                   一键启动入口 (controller / bridge / viewer / simulate / feed)
├── .env.example               配置样例
├── .gitignore                 排除 .env 与日志
├── _recreate_controller.sh    跨平台 controller 容器启动脚本
├── README.md                  本文件（对内说明）
│
├── bridge/                    宿主机 IM 适配层 (核心混合层 / bridge)
│   ├── server.py              HTTP API + Matrix sync 主服务
│   ├── matrix_client.py       Matrix C-S API 客户端 (标准库实现)
│   └── feed_manager.py        admin → @manager DM 投喂工具
│
├── simulator/                 微信群消息模拟器
│   ├── wechat_sim.py          推送脚本 (按 JSON 顺序推送或临时单条)
│   └── messages.json          6 个真实 IT 服务台场景
│
├── viewer/                    浏览器观察页面 (零依赖纯 HTML)
│   ├── index.html             总览
│   ├── agentflow.html         视图一: Agent 对话流 (来自 Matrix 真实事件)
│   └── wechat.html            视图二: 模拟微信群 (员工 ↔ 服务台)
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
| **bridge** | 宿主机 Python | 8770 | IM 适配层 (模拟微信群 ↔ Matrix 房间 ↔ 浏览器) |
| **simulator** | 宿主机 Python (一次性) | — | 推送模拟微信群消息 |

## 设计取舍

- **bridge 用 Python 标准库**: 评审 clone 即可跑, 无需 `pip install`。
- **viewer 用纯 HTML**: 不需要 Node 打包链, 浏览器直接打开。
- **不引入新镜像**: 完全复用官方 `agentteams-embedded:latest`, 改动只发生在 IM 适配层。
- **Manager 提示词即协议**: `prompts/manager-team-prompt.md` 是 ServiceDesk Pilot 的"业务 spec", 把消息包络、4 Worker 职责、自动推进规则写死。
