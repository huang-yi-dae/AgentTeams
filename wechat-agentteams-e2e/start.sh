#!/bin/bash
# =====================================================================
# ServiceDesk Pilot — 一键启动入口
# ---------------------------------------------------------------------
# 用法:
#   ./start.sh controller   # 步骤 1: 启动 controller 容器 (Docker)
#   ./start.sh bridge       # 步骤 2: 启动宿主机桥接服务 (端口 8770)
#   ./start.sh viewer       # 步骤 3: 打开浏览器观察链接
#   ./start.sh simulate     # 步骤 4: 推送 6 条模拟微信群消息
#   ./start.sh all          # 依次执行 controller + bridge + viewer + simulate
#   ./start.sh help         # 帮助
#
# 三进程架构 (S1):
#   [controller] Docker 容器, 包含 Matrix / Higress / Manager / Workers
#   [bridge]     宿主机 Python, 在 Matrix 与浏览器之间做 IM 适配
#   [simulate]   宿主机 Python, 推送微信群消息脚本 (一次性)
# =====================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BRIDGE_PORT=8770
ENV_FILE="$SCRIPT_DIR/.env"
HOST_ENV_FILE="$HOME/agentteams-manager.env"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# --- 检查 .env 是否存在 ---
ensure_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} $ENV_FILE 不存在"
    echo "       首次使用请执行:"
    echo "         cp $SCRIPT_DIR/.env.example $ENV_FILE"
    echo "         # 编辑 $ENV_FILE 填入真实 LLM API Key 等"
    exit 1
  fi
}

# --- 检查端口占用 ---
check_port() {
  local port=$1
  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$port "; then
    echo -e "${YELLOW}[WARN]${NC} 端口 $port 已被占用"
    return 1
  fi
  return 0
}

# --- 等待 controller 就绪 ---
wait_for_controller() {
  echo "[start] 等待 ~/agentteams-manager.env 生成..."
  for i in $(seq 1 60); do
    if [ -f "$HOST_ENV_FILE" ]; then
      echo -e "${GREEN}[ok]${NC} controller 已就绪 ($((i*2))s)"
      return 0
    fi
    sleep 2
  done
  echo -e "${YELLOW}[WARN]${NC} 等待超时 (120s), 但 bridge 仍可手动尝试启动"
  return 1
}

# ============================================================
# 命令: controller
# ============================================================
cmd_controller() {
  ensure_env_file
  echo -e "${GREEN}==> 步骤 1/3: 启动 controller 容器${NC}"
  echo "    端口映射: 18080 (Higress) / 18001 / 18088 / 6167 (Matrix)"
  for p in 18080 18001 18088 6167; do check_port "$p" || true; done

  bash "$SCRIPT_DIR/_recreate_controller.sh"
  wait_for_controller
}

# ============================================================
# 命令: bridge
# ============================================================
cmd_bridge() {
  echo -e "${GREEN}==> 步骤 2/3: 启动宿主机桥接服务${NC}"
  echo "    默认端口: $BRIDGE_PORT"
  check_port "$BRIDGE_PORT" || exit 1

  if [ ! -f "$HOST_ENV_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} $HOST_ENV_FILE 不存在"
    echo "       请先执行:  ./start.sh controller"
    exit 1
  fi

  cd "$SCRIPT_DIR/bridge"
  exec python3 server.py \
    --port "$BRIDGE_PORT" \
    --env-file "$HOST_ENV_FILE" \
    --group-room "微信群-IT服务台支持群"
}

# ============================================================
# 命令: viewer
# ============================================================
cmd_viewer() {
  echo -e "${GREEN}==> 步骤 3/3: 浏览器打开以下链接${NC}"
  echo ""
  echo "    总览页面:       http://127.0.0.1:$BRIDGE_PORT/"
  echo "    Agent 对话流:   http://127.0.0.1:$BRIDGE_PORT/agentflow.html"
  echo "    模拟微信群:     http://127.0.0.1:$BRIDGE_PORT/wechat.html"
  echo ""
  echo "    Higress Console: http://127.0.0.1:18080/"
  echo ""

  # 自动打开默认浏览器 (Linux / WSL / macOS)
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:$BRIDGE_PORT/" 2>/dev/null || true
  elif command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:$BRIDGE_PORT/" 2>/dev/null || true
  fi
}

# ============================================================
# 命令: simulate (可选, 一次性推送 6 条场景消息)
# ============================================================
cmd_simulate() {
  echo -e "${GREEN}==> 推送 6 条模拟微信群消息${NC}"
  echo "    间隔: 90s, 场景: 离职账号 / VPN / MFA / 密码 / GitLab / 打印机"

  if [ ! -f "$HOST_ENV_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} $HOST_ENV_FILE 不存在"
    exit 1
  fi

  # 检查 bridge 是否在跑
  if ! curl -s "http://127.0.0.1:$BRIDGE_PORT/api/status" >/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${NC} bridge 未运行, 请先执行 ./start.sh bridge"
    exit 1
  fi

  cd "$SCRIPT_DIR/simulator"
  exec python3 wechat_sim.py \
    --bridge "http://127.0.0.1:$BRIDGE_PORT" \
    --interval 90 \
    --env-file "$HOST_ENV_FILE" \
    --group-room "微信群-IT服务台支持群"
}

# ============================================================
# 命令: feed (一次性投喂 Manager 组队指令)
# ============================================================
cmd_feed() {
  echo -e "${GREEN}==> 投喂 Manager 组队指令 (DM)${NC}"

  if [ ! -f "$HOST_ENV_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} $HOST_ENV_FILE 不存在"
    exit 1
  fi

  cd "$SCRIPT_DIR/bridge"
  exec python3 feed_manager.py \
    --env-file "$HOST_ENV_FILE" \
    --prompt-file "$SCRIPT_DIR/prompts/manager-team-prompt.md"
}

# ============================================================
# 命令: all (一键全跑)
# ============================================================
cmd_all() {
  cmd_controller

  # 后台拉起 bridge
  cmd_bridge &
  BRIDGE_PID=$!

  # 给 bridge 一点时间起来
  sleep 3

  # 投喂 Manager 组队指令
  cd "$SCRIPT_DIR/bridge"
  python3 feed_manager.py \
    --env-file "$HOST_ENV_FILE" \
    --prompt-file "$SCRIPT_DIR/prompts/manager-team-prompt.md" || true

  cmd_viewer

  echo ""
  echo -e "${GREEN}[ok]${NC} 演示已就绪。"
  echo "      按回车键开始推送 6 条模拟消息..."
  read -r

  cmd_simulate

  echo ""
  echo "[ok] 全部场景已推送, 等待 Manager 处理 (Ctrl+C 退出)"
  wait $BRIDGE_PID
}

# ============================================================
# 帮助
# ============================================================
cmd_help() {
  cat <<EOF
ServiceDesk Pilot — 一键启动入口

用法:
  $0 <command>

Commands:
  controller   步骤 1: 启动 agentteams-embedded 容器 (Docker)
  bridge       步骤 2: 启动宿主机桥接服务 (端口 $BRIDGE_PORT)
  viewer       步骤 3: 打印浏览器观察链接 (3 个页面)
  simulate     推送 6 条模拟微信群消息 (一次性, 默认间隔 90s)
  feed         投喂 Manager 组队指令 (admin → @manager DM)
  all          依次执行 controller + bridge + feed + viewer + simulate
  help         显示本帮助

推荐演示流程 (三进程):
  1) 启动 controller:   $0 controller
  2) 另开终端启动 bridge:    $0 bridge
  3) 浏览器打开:            $0 viewer
  4) 另开终端推送模拟消息:   $0 simulate

依赖:
  - Docker (Docker Desktop on Windows/macOS, Docker Engine on Linux)
  - Python 3.7+ (标准库, 无需 pip install)

首次使用:
  cp .env.example .env
  # 编辑 .env 填入 AGENTTEAMS_LLM_API_KEY 等真实值
  $0 controller
EOF
}

case "${1:-help}" in
  controller) cmd_controller ;;
  bridge)     cmd_bridge ;;
  viewer)     cmd_viewer ;;
  simulate)   cmd_simulate ;;
  feed)       cmd_feed ;;
  all)        cmd_all ;;
  help|-h|--help) cmd_help ;;
  *)
    echo "未知命令: $1"
    cmd_help
    exit 1
    ;;
esac