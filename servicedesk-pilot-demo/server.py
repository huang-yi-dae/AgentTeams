"""
ServiceDesk Pilot —— 服务化运行入口（Docker 形态）

将 Demo 从「单进程读文件一次性跑」升级为「常驻 HTTP 服务」：
  - 宿主机（或企业微信回调）通过 POST /webhook 把群消息逐条推送到容器内服务；
  - 调用 POST /run 触发 AgentTeams 全流程（渠道网关→服务台机器人→Ticket Intake
    标准化→TeamLeader 编排→…→验证→知识沉淀），并导出 HTML/JSON 产物。

这正好坐实方案里的「真实链路」：企业微信回调 webhook 被动推送 → 服务台后端处理
→ 应用消息接口主动下发。对应 opspilot 的 at/ 接入面。

依赖：纯 Python 标准库（http.server / threading / json / urllib 无需）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.trace import Tracer                                            # noqa: E402
from adapters.im_adapter import WeComChannelGateway, ServiceDeskBot      # noqa: E402
from adapters.mcp_gateway import MockMcpGateway                          # noqa: E402
from adapters.approval_adapter import ApprovalAdapter                    # noqa: E402
from skills.knowledge_skills import KnowledgeBase                        # noqa: E402
from agents.orchestrator import TeamLeader                               # noqa: E402
from skills.verify_skills import ObservabilityProbe                      # noqa: E402
from run_demo import (                                                   # noqa: E402
    POLICY_FILE, SYSTEMS_FILE, APPROVERS_FILE, KB_FILE, KB_BASE, OUT_DIR,
    ensure_kb_baseline, reset_kb_to_baseline, _kb_counts_from_file, export_artifacts,
)

# 全局状态
GATEWAY = WeComChannelGateway(None)      # 持久：跨多次 /run 保留 webhook 注入
GATEWAY_LOCK = threading.Lock()
RUNNING = False
POLICY: Dict[str, Any] = {}


def load_policy(approval_mode: str = "") -> Dict[str, Any]:
    with open(POLICY_FILE, "r", encoding="utf-8") as f:
        policy = json.load(f)
    if approval_mode:
        policy.setdefault("approval", {})["mode"] = approval_mode
    policy["verbose"] = False
    policy["_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return policy


def run_once() -> Dict[str, Any]:
    """消费当前 webhook 注入的全部 scenario，跑完整流程并导出产物。"""
    policy = POLICY
    tracer = Tracer(verbose=False)
    bot = ServiceDeskBot(GATEWAY, tracer)
    mcp = MockMcpGateway(SYSTEMS_FILE)
    kb = KnowledgeBase(KB_FILE)
    approval = ApprovalAdapter(APPROVERS_FILE, policy)
    leader = TeamLeader(tracer, policy, GATEWAY, bot, mcp, kb, approval)

    reset_kb_to_baseline()
    kb_before = _kb_counts_from_file(KB_BASE)

    scenarios = GATEWAY.pending_scenarios()
    if not scenarios:
        return {"ok": False, "message": "没有待处理的 webhook 消息，先 POST /webhook"}

    incidents: List[Any] = []
    for sc in scenarios:
        incidents.append(leader.handle_scenario(sc))

    wall = time.time() - tracer.started_at
    metrics = ObservabilityProbe().run(leader.incidents, tracer, wall)
    kb_after = kb.snapshot_counts()
    all_kb_updates: List[Dict[str, Any]] = []
    for inc in incidents:
        all_kb_updates.extend(inc.kb_updates)

    paths = export_artifacts(policy, incidents, tracer, kb, metrics,
                             kb_before, kb_after, all_kb_updates)
    GATEWAY.clear_injected()
    return {
        "ok": True,
        "scenarios": scenarios,
        "metrics": {
            "incidents_total": metrics.get("incidents_total", 0),
            "first_time_resolved": metrics.get("first_time_resolved", 0),
            "escalated": metrics.get("escalated", 0),
            "approval_skipped": metrics.get("approval_skipped", 0),
            "kb_write_backs": metrics.get("kb_write_backs", 0),
        },
        "artifacts": {k: os.path.relpath(v, BASE_DIR) for k, v in paths.items()},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 静默默认访问日志
        return

    def do_GET(self):
        if self.path in ("/", "/health"):
            with GATEWAY_LOCK:
                pending = GATEWAY.pending_scenarios()
            self._send(200, {"status": "ok", "pending_scenarios": pending,
                             "pending_count": len(pending), "running": RUNNING})
        elif self.path == "/trace":
            tp = os.path.join(OUT_DIR, "trace.json")
            if os.path.exists(tp):
                with open(tp, "r", encoding="utf-8") as f:
                    self._send(200, json.load(f))
            else:
                self._send(404, {"error": "no trace yet, POST /webhook then /run"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON body"})
            return

        if self.path == "/webhook":
            try:
                with GATEWAY_LOCK:
                    scenario = GATEWAY.receive_webhook(payload)
                self._send(202, {"ok": True, "scenario": scenario,
                                 "message": "message received, POST /run to process"})
            except ValueError as e:
                self._send(400, {"error": str(e)})
        elif self.path == "/run":
            with GATEWAY_LOCK:
                global RUNNING
                if RUNNING:
                    self._send(409, {"error": "a run is already in progress"})
                    return
                RUNNING = True
            try:
                result = run_once()
            finally:
                with GATEWAY_LOCK:
                    RUNNING = False
            self._send(200, result)
        else:
            self._send(404, {"error": "not found"})


def main() -> int:
    ap = argparse.ArgumentParser(description="ServiceDesk Pilot HTTP 服务（Docker 形态）")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--approval-mode", choices=["manual", "auto_skip", "auto_approve"],
                    default="manual", help="覆盖 policy.json 的 approval.mode")
    args = ap.parse_args()

    global POLICY
    POLICY = load_policy(args.approval_mode)
    ensure_kb_baseline()
    print(f"ServiceDesk Pilot 服务已启动：http://{args.host}:{args.port}")
    print("  POST /webhook  <消息JSON>   接收群消息（模拟企业微信回调推送）")
    print("  POST /run                  触发 AgentTeams 全流程并导出产物")
    print("  GET  /health | /trace | / 状态与链路查看")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
