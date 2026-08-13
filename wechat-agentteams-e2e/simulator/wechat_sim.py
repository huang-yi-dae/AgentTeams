#!/usr/bin/env python3
"""微信群消息模拟器 — 按可配置间隔推送模拟微信群消息到 AgentTeam 并回收回复。"""
import argparse, json, time, uuid, urllib.request, sys, os

WECHAT_ENVELOPE = (
    "[微信群消息] 群: {group} | 成员: {sender} | 消息ID: {mid} | 时间: {ts}\n内容: {text}"
)

def load_messages(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def send_message(base_url, group, sender, text, mid):
    body = WECHAT_ENVELOPE.format(group=group, sender=sender, mid=mid, ts=time.strftime("%H:%M:%S"), text=text)
    req = urllib.request.Request(
        f"{base_url}/api/send",
        data=json.dumps({"group": group, "sender": sender, "text": body}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())

def get_events(base_url, since=0):
    req = urllib.request.Request(f"{base_url}/api/events?since={since}")
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())

def main():
    parser = argparse.ArgumentParser(description="微信群消息模拟器")
    parser.add_argument("--bridge", default="http://127.0.0.1:8770", help="桥接服务地址")
    parser.add_argument("--interval", type=int, default=90, help="推送间隔(秒)")
    parser.add_argument("--scenario", default="default", help="场景: default=所有消息, all=所有")
    parser.add_argument("--group-room", default="微信群-IT服务台支持群", help="目标房间名")
    parser.add_argument("--count", type=int, default=0, help="限制条数(0=全部)")
    parser.add_argument("--text", help="发一条自定义消息")
    parser.add_argument("--sender", default="用户", help="发消息的群成员名")
    parser.add_argument("--watch-only", action="store_true", help="不发送，只观察")
    parser.add_argument("--watch-after", action="store_true", help="发完后观察回复")
    parser.add_argument("--env-file", help="可选 env 文件")
    args = parser.parse_args()

    base_url = args.bridge.rstrip("/")

    if args.text:
        mid = str(uuid.uuid4())
        msg = args.text
        print(f"[sim] 发送 ad-hoc 消息: {msg}")
        resp = send_message(base_url, args.group_room, args.sender, msg, mid)
        print(f"[sim] 已发送 -> {resp.get('event_id','?')}")
        return

    msgs = load_messages(os.path.join(os.path.dirname(__file__), "messages.json"))
    if args.count:
        msgs = msgs[:args.count]

    print(f"[sim] 连接: {base_url}, 房间: {args.group_room}")
    print(f"[sim] {len(msgs)} 条消息, 间隔={args.interval}s\n")

    for i, m in enumerate(msgs):
        mid = str(uuid.uuid4())
        print(f"[sim] [{i+1}/{len(msgs)}] {m['sender']}: {m['text'][:50]}...")
        try:
            resp = send_message(base_url, m["group"], m["sender"], m["text"], mid)
            print(f"     -> OK event={resp.get('event_id','?')}")
        except Exception as e:
            print(f"     -> FAIL: {e}")
        if i < len(msgs) - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
