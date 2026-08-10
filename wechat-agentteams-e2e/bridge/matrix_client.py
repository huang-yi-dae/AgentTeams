#!/usr/bin/env python3
"""最小 Matrix Client-Server API 客户端（纯标准库，零第三方依赖）。"""
import json, os, ssl, urllib.request, urllib.parse


class MatrixClient:
    def __init__(self, base_url, host_header=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.host_header = host_header
        self.timeout = timeout
        self.access_token = None
        self.user_id = None
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def login(self, user, password):
        resp = self._request("POST", "/_matrix/client/v3/login", body={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": user},
            "password": password,
        })
        self.access_token = resp["access_token"]
        self.user_id = resp["user_id"]
        return self.access_token

    def joined_rooms(self):
        return self._request("GET", "/_matrix/client/v3/joined_rooms")["joined_rooms"]

    def room_members(self, room_id):
        return self._request("GET", f"/_matrix/client/v3/rooms/{room_id}/joined_members")["joined"]

    def room_name(self, room_id):
        try:
            ev = self._request("GET", f"/_matrix/client/v3/rooms/{room_id}/state/m.room.name")
            return ev.get("name", room_id)
        except Exception:
            return str(room_id)

    def create_room(self, name=None, is_direct=False, invite=None):
        body = {}
        if name:
            body["name"] = name
        if is_direct:
            body["is_direct"] = True
            body["preset"] = "trusted_private_chat"
        if invite:
            body["invite"] = invite
        resp = self._request("POST", "/_matrix/client/v3/createRoom", body=body)
        return resp["room_id"]

    def invite(self, room_id, user_id):
        return self._request("POST", f"/_matrix/client/v3/rooms/{room_id}/invite", body={"user_id": user_id})

    def send_text(self, room_id, body, msgtype="m.text"):
        txn_id = str(int(os.urandom(4).hex(), 16))
        return self._request("PUT",
            f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            body={"msgtype": msgtype, "body": body},
        )

    def messages(self, room_id, limit=50):
        params = urllib.parse.urlencode({"dir": "b", "limit": limit})
        return self._request("GET", f"/_matrix/client/v3/rooms/{room_id}/messages?{params}")

    def sync(self, since=None, timeout=30000):
        params = {"timeout": str(timeout)}
        if since:
            params["since"] = since
        qs = urllib.parse.urlencode(params)
        return self._request("GET", f"/_matrix/client/v3/sync?{qs}", timeout=timeout + 15)

    def _request(self, method, path, body=None, timeout=None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if self.host_header:
            headers["Host"] = self.host_header
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout or self.timeout, context=self._ssl_ctx) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}


def load_env_file(path=None):
    path = path or os.path.expanduser("~/agentteams-manager.env")
    env = {"__env_file__": path}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def build_client_from_env(env=None):
    env = env or load_env_file()
    gateway_port = env.get("AGENTTEAMS_PORT_GATEWAY", "18080")
    matrix_domain = env.get("AGENTTEAMS_MATRIX_DOMAIN", f"matrix-local.agentteams.io:{gateway_port}")
    base_url = f"http://127.0.0.1:{gateway_port}"
    host = matrix_domain.split(":")[0] if ":" in matrix_domain else matrix_domain
    return MatrixClient(base_url, host_header=f"{host}:{gateway_port}"), env
