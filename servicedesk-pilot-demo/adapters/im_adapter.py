"""
IM Adapter / 渠道接入层（Mock）

对应方案『接入层 / IM Adapter』，并仿照 opspilot 的 at/ 接入面范式，
把「微信接入」真正拆成「渠道接入网关 + 服务台机器人」两层。

真实环境的接入技术现实（重要，决定 Demo 设计）：
- 微信群 / 企业微信群**不能由机器人自由拉取消息，也不能由群机器人主动回复消息**。
- 正确链路：
    ① 企业微信「接收消息」回调 URL（被动 webhook）把用户消息推送到我们的服务台后端；
    ② 服务台后端处理完后，通过企业微信「应用消息接口 / 客服消息接口」主动下发进展与结论。
  （群机器人 webhook 只能由服务端单向往外推文本，不能收消息，因此不承担「接收」职责。）

本模块两个组件，严格对应 opspilot 接入面：
1. WeComChannelGateway —— 渠道接入网关，模拟 ① 接收 + ② 下发 两种接口。
   对外契约保持稳定：fetch_messages() 拉取(推送来的)消息 / push_message() 下发。
2. ServiceDeskBot      —— 服务台机器人(渠道接待)，对应 opspilot『用户进 Team 房间
   @leader』的接待侧：收到消息后做渠道层礼貌应答，并把原始消息打包成
   "待标准化消息"转交 Ticket Intake。它不解析业务、不决定处置。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.models import RawMessage


class WeComChannelGateway:
    """渠道接入网关（仿 opspilot at/ 接入面：Team 房间 + @team_leader 触发）。

    模拟企业微信两类接口：
    - 接收侧：企业微信『接收消息』回调 URL（被动 webhook）。fetch_messages() 对应
      "回调已收到并落库的消息"，而不是机器人去群里拉取。
    - 下发侧：企业微信『应用消息接口 / 客服消息接口』（主动下发）。
      push_message() 对应此，而非群机器人单向往外推。
    """

    DEFAULT_CHANNEL = {
        "type": "wechat_work",
        "chat_id": "wr_it_helpdesk_001",
        "chat_name": "XX科技-IT求助群(全员)",
        "member_count": 186,
    }

    def __init__(self, mock_file: Optional[str] = None):
        if mock_file:
            with open(mock_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            # webhook 模式：无本地文件源，仅接收外部（企业微信回调）推送的消息
            self._data = {"channel": dict(self.DEFAULT_CHANNEL), "messages": []}
        self.channel = self._data["channel"]
        self.sent_replies: List[Dict[str, Any]] = []
        # scenario -> 原始消息 dict 列表（webhook 注入，fetch_messages 取走即清空）
        self._injected: Dict[str, List[Dict[str, Any]]] = {}

    # ---------------- 入站：模拟企业微信回调 webhook 推送 ----------------
    def fetch_messages(self, scenario: Optional[str] = None) -> List[RawMessage]:
        """拉取(企业微信回调推送来的)群消息。scenario 为空表示拉全部。

        接收模式：优先返回 receive_webhook 注入的消息（取走即清空该 scenario）；
        无注入时回退到 mock 文件（单进程一次性跑模式）。
        """
        if self._injected:
            if scenario:
                msgs = self._injected.pop(scenario, [])
            else:
                msgs = [m for ms in self._injected.values() for m in ms]
                self._injected.clear()
            if msgs:
                return self._to_raw(msgs)
        # 回退：本地 mock 文件源（无 webhook 注入时）
        msgs = self._data["messages"]
        if scenario:
            msgs = [m for m in msgs if m.get("scenario") == scenario]
        return self._to_raw(msgs)

    def _to_raw(self, msgs: List[Dict[str, Any]]) -> List[RawMessage]:
        msgs = sorted(msgs, key=lambda m: m["timestamp"])
        return [
            RawMessage(
                msg_id=m["msg_id"],
                scenario=m["scenario"],
                timestamp=m["timestamp"],
                sender=m["sender"],
                msg_type=m["msg_type"],
                content=m["content"],
                attachments=m.get("attachments", []),
                mentions=m.get("mentions", []),
                channel=self.channel,
            )
            for m in msgs
        ]

    # ---------------- 入站增强：接收外部 webhook 推送（分布式/服务化模式）----------------
    def receive_webhook(self, payload: Dict[str, Any]) -> str:
        """模拟企业微信『接收消息』回调 webhook：把一条群消息推送到服务台后端。

        payload 结构与 mock/wechat_messages.json 的 messages[] 完全一致
        （msg_id/scenario/timestamp/sender/content/attachments/mentions）。
        返回该消息所属 scenario，供服务层决定触发哪个工单。
        """
        scenario = payload.get("scenario")
        if not scenario:
            raise ValueError("webhook payload 必须包含 scenario 字段")
        self._injected.setdefault(scenario, []).append(payload)
        return scenario

    def pending_scenarios(self) -> List[str]:
        """已通过 webhook 注入、尚未被 fetch_messages 取走的 scenario 列表。"""
        return list(self._injected.keys())

    def clear_injected(self) -> None:
        """清空 webhook 注入缓冲（通常在一轮 /run 消费后调用）。"""
        self._injected.clear()

    def list_scenarios(self) -> List[str]:
        seen, out = set(), []
        for m in sorted(self._data["messages"], key=lambda x: x["timestamp"]):
            if m["scenario"] not in seen:
                seen.add(m["scenario"])
                out.append(m["scenario"])
        for sc in self._injected:
            if sc not in seen:
                seen.add(sc)
                out.append(sc)
        return out

    # ---------------- 出站：模拟企业微信应用消息接口 / 客服消息接口下发 ----------------
    def push_message(self, incident_id: str, text: str, at_user: str = "") -> Dict[str, Any]:
        """把进展/结论通过企业微信应用消息接口主动下发（非群机器人单向往外推）。"""
        rec = {
            "incident_id": incident_id,
            "chat_id": self.channel["chat_id"],
            "channel": self.channel["type"],
            "at_user": at_user,
            "text": text,
            "delivery": "wecom_app_message_api",  # 明确标注下发通道，区别于群机器人 webhook
        }
        self.sent_replies.append(rec)
        return rec


class ServiceDeskBot:
    """服务台机器人（渠道接待 / 仿 opspilot『用户进 Team 房间 @leader』的接待侧）。

    职责边界：只做渠道层接待与消息转交，不解析业务、不决定处置方案。
    - acknowledge():        收到消息后礼貌应答，让用户知道工单已受理
    - deliver_conclusion(): 处置结论经应用消息接口下发（由 TeamLeader 收尾时调用）
    - wrap_for_intake():    把(webhook 推送来的)原始消息原样打包给 Ticket Intake
    """

    name = "ServiceDesk Bot"

    def __init__(self, gateway: WeComChannelGateway, tracer):
        self.gw = gateway
        self.tracer = tracer

    def acknowledge(self, incident_id: str, reporter_name: str) -> Dict[str, Any]:
        text = f"@{reporter_name} 您好，我是服务台机器人，已收到您的报障，正在生成工单…"
        rec = self.gw.push_message(incident_id, text, at_user=reporter_name)
        self.tracer.im("outbound", self.name, text)
        return rec

    def deliver_conclusion(self, incident_id: str, text: str, reporter_name: str) -> Dict[str, Any]:
        rec = self.gw.push_message(incident_id, text, at_user=reporter_name)
        self.tracer.im("outbound", self.name, text)
        return rec

    def wrap_for_intake(self, messages: List[RawMessage]) -> List[RawMessage]:
        """把原始消息原样打包给 Ticket Intake（不做任何业务解析）。"""
        self.tracer.note(f"{self.name} 移交 {len(messages)} 条原始消息给 Ticket Intake Agent"
                         f"（接待层不做业务解析，标准化由 Intake 负责）")
        return messages
