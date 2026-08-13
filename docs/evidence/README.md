# 运行证据（Evidence）

本目录用于存放 ServiceDesk Pilot 端到端跑通后的留底材料。

## 期望文件清单

| 文件 | 期望内容 | 采集方法 |
|---|---|---|
| `bridge.log` | 宿主机桥接服务的完整 stdout（admin 登录、网关房就绪、6 轮"收消息→拆解→回复"日志） | `./start.sh bridge > ../docs/evidence/bridge.log 2>&1` |
| `viewer-index.png` | 总览页面截图 | 浏览器截图 |
| `viewer-agentflow.png` | Agent 对话流截图 | 浏览器截图 |
| `viewer-wechat.png` | 模拟微信群截图 | 浏览器截图 |
| `container-logs.txt` | controller 容器尾部 200 行日志 | `docker logs agentteams-controller \| tail -200 > ../docs/evidence/container-logs.txt` |
| `matrix-rooms.json` | Matrix 房间与最近事件快照 | 通过 Higress Console API 导出 |
| `demo-recording.mp4` | 完整演示录像（可选） | 录屏工具（OBS / Windows Game Bar） |

## 采集顺序

1. 启动 controller 与 bridge（参考 RUNBOOK）
2. 打开三个 viewer 页面，逐页截图保存
3. 推送 6 条场景消息，等待 Manager 处理完成
4. 关闭 bridge 进程（Ctrl+C）
5. 把 stdout 重定向文件 `bridge.log` 复制到此目录
6. 用 `docker logs` 命令导出 container 日志

## 验证完整性

跑通后建议检查：

- [ ] `bridge.log` 中能看到 `[bridge] admin login OK`
- [ ] `bridge.log` 中能看到 `网关房已就绪: 微信群-IT服务台支持群`
- [ ] `bridge.log` 中能看到至少 6 条 `wechat_inbound` 记录
- [ ] `bridge.log` 中能看到至少 6 条 `wechat_reply` 记录
- [ ] `viewer-wechat.png` 中显示完整对话（含服务台回复）
- [ ] `container-logs.txt` 无 ERROR / FATAL 关键字
