#!/usr/bin/env python3
"""桥接服务 — 登录容器 Matrix，同步真实事件，提供双视图 + JSON API。"""
import argparse, json, os, sys, threading, time, http.server, re
from matrix_client import build_client_from_env, load_env_file


def parse_wechat_envelope(body):
    """从微信群消息包络正文解析结构化字段。包络格式见 wechat_sim.WECHAT_ENVELOPE。
    用分步 search 而非单个巨型正则，避免惰性回溯在 `|` 分隔字段上失败 (曾导致 text 解析不出)。"""
    if "[微信群消息]" not in body:
        return None
    d = {}
    for key, pat in [
        ("group",  r"群:\s*([^\n|]+)"),
        ("sender", r"成员:\s*([^\n|]+)"),
        ("mid",    r"消息ID:\s*(\S+)"),
        ("ts",     r"时间:\s*([^\n]+)"),
        ("text",   r"内容:\s*(.*)"),
    ]:
        m = re.search(pat, body, re.DOTALL)
        if m:
            d[key] = m.group(1).strip()
    return d or None



class EventStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = []
        self._seq = 0

    def append(self, **kwargs):
        with self._lock:
            self._seq += 1
            rec = {"seq": self._seq, "ts": int(time.time() * 1000), **kwargs}
            self._events.append(rec)
            return rec

    def since(self, since_seq):
        with self._lock:
            return [e for e in self._events if e["seq"] > since_seq]

    @property
    def all(self):
        with self._lock:
            return list(self._events)

    @property
    def last_seq(self):
        return self._seq

    def clear(self):
        with self._lock:
            self._events.clear()
            self._seq = 0
            return {"seq": 0, "ts": int(time.time() * 1000), "kind": "reset"}


class Bridge:
    def __init__(self, client, env, gateway_room_name, port):
        self.client = client
        self.env = env
        self.gateway_room_name = gateway_room_name
        self.port = port
        self.store = EventStore()
        self.admin_user = env.get("AGENTTEAMS_ADMIN_USER", "admin")
        self.admin_pass = env.get("AGENTTEAMS_ADMIN_PASSWORD")
        self.sync_token = None
        self._running = False

    def connect(self):
        print(f"[bridge] env file      : {self.env.get('__env_file__')}")
        print(f"[bridge] matrix connect: {self.client.base_url} (Host: {self.client.host_header})")
        self.client.login(self.admin_user, self.admin_pass)
        print(f"[bridge] admin login OK -> {self.client.user_id}")
        self.ensure_gateway_room()

    def ensure_gateway_room(self):
        manager_id = "@manager:matrix-local.agentteams.io:18080"
        rooms = self.client.joined_rooms()
        for rid in rooms:
            if self.client.room_name(rid) == self.gateway_room_name:
                print(f"[bridge] gateway room: {rid} -> {self.gateway_room_name}")
                self.gateway_room_id = rid
                return

        print(f"[bridge] 创建网关房间: {self.gateway_room_name}")
        rid = self.client.create_room(name=self.gateway_room_name, invite=[manager_id])
        self.gateway_room_id = rid
        self.store.append(kind="gateway_progress", room_id=rid, sender=self.client.user_id,
                          body=f"网关房已就绪: {self.gateway_room_name}")

    def bootstrap_history(self):
        for rid in self.client.joined_rooms():
            room_label = self.client.room_name(rid)
            try:
                msgs = self.client.messages(rid, limit=20)
                for ev in msgs.get("chunk", []):
                    self._record_event(ev, rid, room_label)
            except Exception:
                pass

    def sync_loop(self):
        self._running = True
        while self._running:
            try:
                resp = self.client.sync(since=self.sync_token, timeout=30000)
                self.sync_token = resp.get("next_batch", self.sync_token)
                rooms_data = resp.get("rooms", {}).get("join", {})
                for rid, data in rooms_data.items():
                    room_label = self.client.room_name(rid)
                    for ev in data.get("timeline", {}).get("events", []):
                        self._record_event(ev, rid, room_label)
            except Exception as e:
                if self._running:
                    print(f"[bridge] sync error: {e}")
                    time.sleep(5)

    def _record_event(self, ev, room_id, room_label):
        sender = ev.get("sender", "?")
        body = ev.get("content", {}).get("body", "") or str(ev.get("type", ""))
        sender_local = sender.split(":")[0].lstrip("@")

        role = "admin" if sender_local == self.admin_user else (
            "manager" if "manager" in sender_local else "worker"
        )

        rec = {
            "event_id": ev.get("event_id", "?"),
            "room_id": room_id,
            "room_label": room_label,
            "sender": sender,
            "sender_local": sender_local,
            "role": role,
            "body": body,
            "kind": "agent_flow",
        }

        # 识别微信群消息包络
        wechat = parse_wechat_envelope(body)
        if wechat:
            rec["kind"] = "wechat_inbound"
            rec["wechat"] = wechat
        elif body.startswith("[群回复]"):
            rec["kind"] = "wechat_reply"
        elif role == "manager" and room_label == self.gateway_room_name:
            # 兜底: Manager 在网关房里发的消息 = 给微信群的回复,
            # 不依赖 [群回复] 前缀 (LLM 经常省略前缀).
            rec["kind"] = "wechat_reply"
        elif room_label == self.gateway_room_name:
            rec["kind"] = "gateway_progress"

        self.store.append(**rec)


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    bridge = None

    def do_GET(self):
        if self.path == "/":
            self._serve_file("../viewer/index.html", "text/html")
        elif self.path == "/wechat.html":
            self._serve_file("../viewer/wechat.html", "text/html")
        elif self.path == "/agentflow.html":
            self._serve_file("../viewer/agentflow.html", "text/html")
        elif self.path == "/api/status":
            self._json({"rooms": list(self.bridge.client.joined_rooms()), "last_sync": time.time()})
        elif self.path.startswith("/api/events"):
            qs = self.path.split("?")[1] if "?" in self.path else ""
            params = dict(p.split("=") for p in qs.split("&") if "=" in p)
            since = int(params.get("since", 0))
            self._json(self.bridge.store.since(since))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/send":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            text = data.get("text", "")
            rid = self.bridge.gateway_room_id
            resp = self.bridge.client.send_text(rid, text)
            self._json({"event_id": resp.get("event_id"), "sent": True})
        elif self.path == "/api/reset":
            rec = self.bridge.store.clear()
            self._json({"cleared": True, "seq": rec["seq"], "ts": rec["ts"]})
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel_path, mime):
        abs_path = os.path.join(os.path.dirname(__file__), rel_path)
        try:
            with open(abs_path, encoding="utf-8") as f:
                content = f.read().encode()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7890)
    parser.add_argument("--env-file", help="env 文件路径")
    parser.add_argument("--group-room", default="微信群-IT服务台支持群")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    client, env = build_client_from_env(env)

    bridge = Bridge(client, env, args.group_room, args.port)
    bridge.connect()
    bridge.bootstrap_history()

    # 后台 sync
    syncer = threading.Thread(target=bridge.sync_loop, daemon=True)
    syncer.start()

    # HTTP 服务
    BridgeHandler.bridge = bridge
    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), BridgeHandler)
    print(f"[bridge] 视图: http://127.0.0.1:{args.port}/")
    print(f"[bridge] 视图一 Agent 对话流: http://127.0.0.1:{args.port}/agentflow.html")
    print(f"[bridge] 视图二 微信群: http://127.0.0.1:{args.port}/wechat.html")
    server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
