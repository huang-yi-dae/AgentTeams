#!/usr/bin/env bash
# ServiceDesk demo 宿主进程拉起 + 健康检查（bridge 前端 + token 刷新循环）
# 用法: bash start-demo-host.sh [env_file] [port]
# 注意：bridge 与 token 循环都是「宿主机进程」，不在 Docker 内，会话结束即失联，需每次冷启动重跑本脚本。
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${1:-$HOME/agentteams-manager.env}"
PORT="${2:-7890}"
CONTROLLER=agentteams-controller
# 注意：不能用 cygpath -w 生成路径——Git Bash 下它会产出带 NUL 字节的路径，
# 导致重定向 `> file` 静默失败（host token 文件永远不更新 -> manager 派单 401）。
# 直接用 $HOME（Git Bash 能正确重定向到 /c/Users/... 真实文件）。
TOKEN_FILE="$HOME/agentteams-auth-token"

echo "[demo] env=$ENV_FILE port=$PORT"

echo "[demo] 1) token 刷新循环 (docker exec cat，不能用 docker cp -> bind 挂载文件静默不生效)"
# 停掉可能残留的旧循环（含失效的 docker cp 版本）
pkill -f "cli-token" 2>/dev/null || true
sleep 1
nohup bash -c "while true; do docker exec $CONTROLLER cat /var/run/agentteams/cli-token > \"$TOKEN_FILE\" 2>/dev/null; sleep 20; done" > /tmp/token-loop.log 2>&1 < /dev/null &
echo "[demo]    token loop pid $!"

echo "[demo] 2) bridge 前端"
if curl -s -o /dev/null --max-time 3 "http://localhost:$PORT/api/status"; then
  echo "[demo]    bridge 已在运行"
else
  nohup python "$SCRIPT_DIR/bridge/server.py" --port "$PORT" --env-file "$ENV_FILE" > /tmp/bridge.log 2>&1 &
  echo "[demo]    bridge pid $!"
  sleep 4
fi

echo "[demo] 3) 健康检查"
for p in / /wechat.html /agentflow.html /api/status /api/events; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:$PORT$p")
  echo "  $p -> $code"
done
h=$(head -c 40 "$TOKEN_FILE" 2>/dev/null); c=$(docker exec "$CONTROLLER" head -c 40 /var/run/agentteams/cli-token 2>/dev/null)
if [ "$h" = "$c" ]; then echo "[demo] token: SYNCED (manager 派单不会 401)"; else echo "[demo] token: DIFF (警告，manager 可能 401)"; fi
echo "[demo] done. 浏览器: http://localhost:$PORT/  (微信群视图: http://localhost:$PORT/wechat.html)"
