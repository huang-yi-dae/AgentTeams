# ServiceDesk Pilot Demo — 历史证据快照 (2026-08-13)

> ⚠️ **这是 2026-08-13 跑通 ServiceDesk Pilot 纯 Python demo 的固定快照，不是再生证据。**
>
> 任何人重新跑 `servicedesk-pilot-demo/run_demo.py`，产物会落到 `servicedesk-pilot-demo/out/`（已在 .gitignore 忽略），**不会**更新本目录。
>
> 本目录的文件：
> - 包含特定时间戳 / UUID / token 等不可重现字段
> - 作为「过去跑通」的留证被保留
> - 评审时仅作参考；不要期望与本机新跑结果一致

## 文件清单

| 文件 | 内容 |
|---|---|
| `dashboard.html` | 亮色主题可视化看板（泳道图 / 审批卡 / 知识库 diff / 调用链） |
| `report.md` | 文字版复盘报告 |
| `trace.json` | 全链路 Trace（可被 HTML 看板回放） |
| `e2e-verification-2026-08-13.md` | e2e 跑通验证记录（容器状态、浏览器端点、Manager 处理结果） |
| `run-2026-08-13-bridge-events.txt` | Bridge 事件流快照 |
| `run-2026-08-13-containers.txt` | 容器状态快照 |
| `run-2026-08-13-group-messages.txt` | 微信群消息快照 |
| `run-2026-08-13-workers.txt` | Worker 状态快照 |

## 如何在自己的机器上重新生成证据

```powershell
cd servicedesk-pilot-demo
python run_demo.py --approval-mode auto_skip
# 产物落在 out/ 目录:
#   out/trace.json, out/report.md, out/dashboard.html
# 不会被 commit 到 git（已在 .gitignore）
```

## 对比 evidence 留证 vs 实时产物

| 用途 | 用哪个 |
|---|---|
| 评审 / 答辩时证明"过去跑通过" | `docs/evidence/servicedesk-demo/` (本目录) |
| 自己调试时看当前运行情况 | `servicedesk-pilot-demo/out/` |
| 上游 ServiceDesk Pilot e2e demo | `docs/evidence/wechat-e2e/` (本次会话新增) |