"""
ServiceDesk Pilot - 对话式可视化（聊天气泡视图）

把 trace.json 里 TeamLeader / 各职能 Agent / 报障人 / 审批人 / 系统 MCP 工具
的发言，渲染成「群聊」式气泡界面，谁说了什么一眼可读。

亮色主题，纯静态 HTML（复用已导出的 out/trace.json），无需浏览器服务、无需 API key。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "out")
TRACE_PATH = os.path.join(OUT_DIR, "trace.json")

# --------------------------------------------------------------------------
# 角色定义：key -> (展示名, 头像, css 类)
# --------------------------------------------------------------------------
ROLE = {
    "teamleader": ("TeamLeader · 中枢调度", "TL", "tl"),
    "intake":     ("Ticket Intake",          "TI", "intake"),
    "knowledge":  ("Knowledge",             "KB", "knowledge"),
    "triage":     ("Triage Analyst",         "TA", "triage"),
    "resolution": ("Resolution",             "RS", "resolution"),
    "verify":     ("Verify",                 "VF", "verify"),
    "approver":   ("审批人",                  "✓",  "approver"),
    "user":       ("报障人",                  "👤", "user"),
    "bot":        ("服务台机器人",            "🤖", "bot"),
    "system":     ("系统",                    "⚙",  "system"),
}


def _esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _norm(name: str) -> str:
    n = (name or "").lower()
    for k in ("teamleader", "intake", "knowledge", "triage", "resolution", "verify"):
        if k in n:
            return k
    return "system"


def _sys_text(ev: Dict[str, Any]) -> str:
    kind = ev["kind"]
    d = ev.get("detail") or {}
    if kind == "tool":
        return f"{_esc(d.get('system_id', ''))}.{_esc(ev['name'])} → {_esc(d.get('summary', ''))}"
    if kind == "rag":
        gap = " ⚠ 无有效召回，标记知识缺口" if d.get("gap") else ""
        return f"RAG 检索「{_esc(d.get('query', ''))}」命中 {d.get('hits', 0)} 条{gap}"
    if kind == "kb":
        return f"知识库 {_esc(ev['name'])}: {_esc(d.get('target', ''))}"
    if kind == "skill":
        return f"Skill {_esc(ev['name'])}: {_esc(d.get('summary', ''))}"
    return _esc(ev.get("name", ""))


def _role_of(ev: Dict[str, Any]):
    """返回 (role_key, speaker_override_or_None, text)"""
    kind = ev["kind"]
    name = ev.get("name", "")
    d = ev.get("detail") or {}
    if kind == "im":
        if name == "inbound":
            return "user", d.get("who", "报障人"), d.get("text", "")
        return "bot", "服务台机器人", d.get("text", "")
    if kind == "agent":
        key = _norm(name)
        return key, None, d.get("action", "")
    if kind == "approval":
        return "approver", None, name
    # tool / rag / kb / skill / note / metric / stage_end -> 系统动作
    return "system", None, _sys_text(ev)


def _side_of(role_key: str) -> str:
    if role_key in ("user", "approver"):
        return "left"
    # system 动作本质上是服务台/Agent 侧后台行为，和 Agent 同侧靠右对齐，避免居中导致错位
    return "right"  # 各 Agent + 机器人 + 系统动作 靠右


def _incident_meta(inc: Any) -> Dict[str, str]:
    cat = inc.classification.category if inc.classification else "-"
    risk = inc.triage.risk_level.value if inc.triage else "-"
    concl = inc.verification.conclusion if inc.verification else "-"
    return {"id": inc.incident_id, "scenario": inc.scenario,
            "category": cat, "risk": risk, "conclusion": concl}


def write_chat(path: str, policy: Dict[str, Any],
               incidents: List[Any], metrics: Dict[str, Any]) -> str:
    # 读 trace
    with open(TRACE_PATH, "r", encoding="utf-8") as f:
        trace = json.load(f)
    events = trace.get("events", [])

    mode = policy.get("approval", {}).get("mode", "manual")
    run_at = policy.get("_run_at", "")
    n_sc = len(incidents)

    # KPI 卡片
    kpi = [
        ("工单", metrics.get("incidents_total", 0), ""),
        ("解决", metrics.get("first_time_resolved", 0), "ok"),
        ("升级", metrics.get("escalated", 0), "fail"),
        ("免审批", metrics.get("approval_skipped", 0), "skip"),
        ("MCP调用", metrics.get("mcp_tool_calls", 0), "info"),
        ("知识写回", metrics.get("kb_write_backs", 0), "info"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-v {k[2]}">{k[1]}</div>'
        f'<div class="kpi-l">{_esc(k[0])}</div></div>' for k in kpi)

    # 每个工单一个聊天面板
    chats_html = ""
    for inc in incidents:
        meta = _incident_meta(inc)
        evs = [e for e in events if e.get("incident_id") == meta["id"]]
        bubbles = ""
        for e in evs:
            role_key, speaker, text = _role_of(e)
            disp_name, avatar, cls = ROLE.get(role_key, ROLE["system"])
            speaker_label = speaker if speaker else disp_name
            side = _side_of(role_key)
            status_cls = {"fail": "fail", "skipped": "skip"}.get(e.get("status"), "")
            bubbles += (
                f'<div class="row {side}">'
                f'<div class="av {cls}">{_esc(avatar)}</div>'
                f'<div class="bub {cls} {status_cls}">'
                f'<div class="who">{_esc(speaker_label)}</div>'
                f'<div class="txt">{_esc(text)}</div>'
                f'<div class="time">{_esc(e.get("at", ""))}</div>'
                f'</div></div>')
        concl_pill = {"success": "ok", "partial": "skip", "failed": "fail",
                      "not_applicable": "warn"}.get(meta["conclusion"], "info")
        chats_html += (
            f'<div class="chat">'
            f'<div class="chat-h"><span class="cid">{_esc(meta["id"])}</span>'
            f'<span class="csc">{_esc(meta["scenario"])}</span>'
            f'<span class="cpill r{meta["risk"]}">风险 {_esc(meta["risk"])}</span>'
            f'<span class="cpill cat">{_esc(meta["category"])}</span>'
            f'<span class="cpill {concl_pill}">{_esc(meta["conclusion"])}</span>'
            f'<span class="cnt">{len(evs)} 条对话</span></div>'
            f'<div class="chat-body">{bubbles}</div></div>')

    # 图例
    legend = "".join(
        f'<span class="lg {c}"><i>{_esc(a)}</i>{_esc(n)}</span>'
        for n, a, c in [ROLE[k][0:3] for k in
                    ("user", "bot", "teamleader", "intake", "knowledge",
                     "triage", "resolution", "verify", "approver", "system")])

    html = CHAT_HTML_TEMPLATE
    html = (html.replace("[[RUN_AT]]", _esc(run_at))
                .replace("[[MODE]]", _esc(mode))
                .replace("[[SCENARIOS]]", str(n_sc))
                .replace("[[KPI]]", kpi_html)
                .replace("[[LEGEND]]", legend)
                .replace("[[CHATS]]", chats_html))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# --------------------------------------------------------------------------
# HTML 模板（CSS 大括号用普通字符串，避免 f-string 转义）
# --------------------------------------------------------------------------
CHAT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ServiceDesk Pilot · Agent 对话视图</title>
<style>
  :root {
    --bg:#f4f6f9; --panel:#fff; --ink:#1f2328; --muted:#656d76; --line:#d8dee4;
    --tl:#7c3aed; --intake:#0969da; --knowledge:#0d9488; --triage:#ea580c;
    --resolution:#16a34a; --verify:#db2777; --approver:#b45309; --user:#475569;
    --bot:#2563eb; --system:#6b7280;
    --bubble-user:#eef1f5; --bubble-agent:#eef4ff;
  }
  * { box-sizing:border-box; }
  body { font-family:-apple-system,"Segoe UI","Microsoft YaHei",Helvetica,Arial,sans-serif;
    background:var(--bg); color:var(--ink); margin:0; padding:22px; line-height:1.5; }
  .wrap { max-width:900px; margin:0 auto; }
  h1 { font-size:21px; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:14px; }
  .kpis { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:14px; }
  .kpi { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:10px 14px; min-width:92px; flex:1; }
  .kpi-v { font-size:22px; font-weight:700; }
  .kpi-v.ok { color:var(--resolution); } .kpi-v.fail { color:#cf222e; }
  .kpi-v.skip { color:var(--approver); } .kpi-v.info { color:var(--intake); }
  .kpi-l { font-size:12px; color:var(--muted); margin-top:2px; }
  .legend { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; font-size:12px; }
  .lg { display:inline-flex; align-items:center; gap:5px; color:var(--muted); }
  .lg i { width:20px; height:20px; line-height:20px; text-align:center; border-radius:50%;
    color:#fff; font-style:normal; font-size:11px; font-weight:700; }
  .lg.tl i { background:var(--tl); } .lg.intake i { background:var(--intake); }
  .lg.knowledge i { background:var(--knowledge); } .lg.triage i { background:var(--triage); }
  .lg.resolution i { background:var(--resolution); } .lg.verify i { background:var(--verify); }
  .lg.approver i { background:var(--approver); } .lg.user i { background:var(--user); }
  .lg.system i { background:var(--system); }
  .chat { background:var(--panel); border:1px solid var(--line); border-radius:12px;
    margin-bottom:18px; overflow:hidden; }
  .chat-h { display:flex; align-items:center; flex-wrap:wrap; gap:8px;
    padding:11px 14px; background:#fafbfc; border-bottom:1px solid var(--line);
    font-size:13px; }
  .cid { font-weight:700; } .csc { color:var(--muted); }
  .cnt { margin-left:auto; color:var(--muted); font-size:12px; }
  .cpill { display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px;
    font-weight:600; border:1px solid var(--line); }
  .cpill.ok { background:#e6f4ea; color:var(--resolution); }
  .cpill.fail { background:#ffebe9; color:#cf222e; }
  .cpill.skip { background:#fff8c5; color:var(--approver); }
  .cpill.warn { background:#fff1e6; color:#bc4c00; }
  .cpill.info { background:#ddf4ff; color:var(--intake); }
  .cpill.rL0 { background:#eaeef2; color:var(--muted); }
  .cpill.rL1 { background:#ddf4ff; color:var(--intake); }
  .cpill.rL2 { background:#fff1e6; color:#bc4c00; }
  .cpill.rL3 { background:#ffebe9; color:#cf222e; }
  .cpill.cat { background:#f3f4f6; color:var(--muted); }
  .chat-body { padding:14px 16px; }
  .row { display:flex; gap:9px; margin-bottom:12px; align-items:flex-start; }
  .row.left { flex-direction:row; } .row.right { flex-direction:row-reverse; }
  .row.center { justify-content:center; }
  .av { width:34px; height:34px; min-width:34px; line-height:34px; text-align:center;
    border-radius:50%; color:#fff; font-weight:700; font-size:13px; }
  .av.tl { background:var(--tl); } .av.intake { background:var(--intake); }
  .av.knowledge { background:var(--knowledge); } .av.triage { background:var(--triage); }
  .av.resolution { background:var(--resolution); } .av.verify { background:var(--verify); }
  .av.approver { background:var(--approver); } .av.user { background:var(--user); }
  .av.bot { background:var(--bot); } .av.system { background:var(--system); font-size:15px; }
  .bub { max-width:74%; padding:9px 12px; border-radius:12px; font-size:13.5px; }
  .row.left .bub { background:var(--bubble-user); border-top-left-radius:3px; }
  .row.right .bub { background:var(--bubble-agent); border-top-right-radius:3px; }
  .row.right .bub.tl { border:1px solid #e4d4fb; }
  .row.right .bub.triage { border:1px solid #fbd9c0; }
  .row.right .bub.verify { border:1px solid #f7c6e0; }
  .row.right .bub.resolution { border:1px solid #c7ebd2; }
  .row.right .bub.knowledge { border:1px solid #bfe6e1; }
  .row.right .bub.intake { border:1px solid #c4ddf7; }
  .row.right .bub.bot { background:#e7f0ff; }
  .bub.system { background:#f3f4f6; color:var(--muted); font-size:12px;
    border-radius:8px; padding:6px 11px; }
  .bub.fail { border:1px solid #f0b3b8; }
  .bub.skip { border:1px solid #ecd98a; }
  .row.center .bub { background:#f3f4f6; color:var(--muted); font-size:12px;
    max-width:88%; border-radius:8px; padding:5px 11px; }
  .who { font-size:11.5px; font-weight:700; color:var(--muted); margin-bottom:3px; }
  .row.right .who { text-align:right; }
  .bub.tl .who { color:var(--tl); } .bub.intake .who { color:var(--intake); }
  .bub.knowledge .who { color:var(--knowledge); } .bub.triage .who { color:var(--triage); }
  .bub.resolution .who { color:var(--resolution); } .bub.verify .who { color:var(--verify); }
  .bub.approver .who { color:var(--approver); } .bub.user .who { color:var(--user); }
  .bub.bot .who { color:var(--bot); }
  .txt { white-space:pre-wrap; word-break:break-word; }
  .time { font-size:10.5px; color:var(--muted); margin-top:4px; text-align:right; }
</style></head>
<body><div class="wrap">
  <h1>ServiceDesk Pilot · Agent 对话视图</h1>
  <div class="sub">GOAI Agent Infra 赛道初赛 Demo · 运行时间 [[RUN_AT]] ·
    审批模式 <b>[[MODE]]</b> · 场景数 [[SCENARIOS]]</div>

  <div class="kpis">[[KPI]]</div>
  <div class="legend">[[LEGEND]]</div>

  [[CHATS]]
</div></body></html>"""
