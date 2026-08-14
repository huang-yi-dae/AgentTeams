#!/usr/bin/env python3
"""管理员→@Manager DM 投喂工具 — 将 prompts/manager-team-prompt.md 以私信送达 Manager。"""
import sys, os, argparse, time

sys.path.insert(0, os.path.dirname(__file__))
from matrix_client import build_client_from_env, load_env_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="agentteams env 文件路径")
    parser.add_argument("--prompt-file", default=os.path.join(os.path.dirname(__file__), "..", "prompts", "manager-team-prompt.md"))
    parser.add_argument("--wait", type=int, default=60, help="等待 Manager 回复的时间(秒)")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    client, env = build_client_from_env(env)

    admin_user = env.get("AGENTTEAMS_ADMIN_USER", "admin")
    admin_pass = env.get("AGENTTEAMS_ADMIN_PASSWORD")
    if not admin_pass:
        print("ERROR: AGENTTEAMS_ADMIN_PASSWORD not found in env")
        return 1

    print(f"[feed] 登录 admin...")
    client.login(admin_user, admin_pass)
    print(f"[feed] 登录成功: {client.user_id}")

    # 找或创建 @manager 的 DM 房间
    rooms = client.joined_rooms()
    dm_room = None
    for rid in rooms:
        members = client.room_members(rid)
        if "@manager" in members or "manager" in members:
            dm_room = rid
            print(f"[feed] 已有 DM 房间: {rid}")
            break

    if not dm_room:
        print("[feed] 创建 DM 房间...")
        dm_room = client.create_room(is_direct=True, invite=["@manager:matrix-local.agentteams.io:18080"])
        print(f"[feed] DM 房间已创建: {dm_room}")

    # 读提示词并发送
    prompt_path = os.path.abspath(args.prompt_file)
    with open(prompt_path, encoding="utf-8") as f:
        content = f.read()

    # 只发正文（跳过 YAML 头部说明）
    lines = content.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.strip() == "## 正文":
            start = i + 1
            break
    body = "\n".join(lines[start:]).strip()

    print(f"[feed] 发送组队指令 ({len(body)} 字符)...")
    client.send_text(dm_room, body)
    print("[feed] 已发送，等待 Manager 回复...")

    time.sleep(args.wait)

    # 看回复（过滤空 body / 非文本事件，只取最近一条有效文本）
    msgs = client.messages(dm_room, limit=10)
    replies = []
    for ev in msgs.get("chunk", []):
        if ev.get("sender") == client.user_id:
            continue
        if ev.get("type") != "m.room.message":
            continue
        body = ev.get("content", {}).get("body", "").strip()
        if body:
            replies.append(body)
    if replies:
        print(f"\n[manager 回复] {replies[0][:400]}")
    else:
        print("\n[manager 回复] (等待窗口内未收到非空文本回复，可去 http://localhost:7890/wechat.html 查看)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
