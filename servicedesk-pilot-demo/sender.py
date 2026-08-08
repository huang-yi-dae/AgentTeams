"""
ServiceDesk Pilot —— 宿主机消息模拟器（Docker 形态配套）

模拟「微信群里的员工发言」：从 mock/wechat_messages.json 按 scenario 读取消息，
逐条 POST 到容器的 POST /webhook（对应真实环境的企业微信回调推送），
最后 POST /run 触发 AgentTeams 处理，并打印返回的处置摘要。

纯标准库（urllib.request），零依赖。

用法：
  python sender.py                       # 全部场景发到 localhost:8080
  python sender.py --host 127.0.0.1 --port 8080
  python sender.py --scenario S1_vpn_locked
  python sender.py --file mock/wechat_messages.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WECHAT_FILE = os.path.join(BASE_DIR, "mock", "wechat_messages.json")


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="ServiceDesk Pilot 宿主机消息模拟器")
    ap.add_argument("--host", default="localhost", help="server 地址")
    ap.add_argument("--port", type=int, default=8080, help="server 端口")
    ap.add_argument("--scenario", help="只发送指定 scenario（默认全部）")
    ap.add_argument("--file", default=WECHAT_FILE, help="消息源 JSON 文件")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)
    msgs = data["messages"]
    if args.scenario:
        msgs = [m for m in msgs if m.get("scenario") == args.scenario]

    if not msgs:
        print("没有可发送的消息（检查 --scenario / --file）")
        return 1

    base = f"http://{args.host}:{args.port}"
    print(f"→ 推送 {len(msgs)} 条群消息到 {base}/webhook")
    for m in msgs:
        # webhook payload 与 mock 消息结构一致（msg_id/scenario/timestamp/...）
        post_json(f"{base}/webhook", m)
        snippet = m["content"][:32].replace("\n", " ")
        print(f"  · [{m['scenario']}] {m['sender']['name']}: {snippet}")

    print(f"→ 触发处理 POST {base}/run ...")
    result = post_json(f"{base}/run", {})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
