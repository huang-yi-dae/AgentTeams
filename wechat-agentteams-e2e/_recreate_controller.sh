#!/bin/bash
# =====================================================================
# _recreate_controller.sh — 启动 agentteams-embedded 容器（跨平台）
# ---------------------------------------------------------------------
# 由 start.sh 调用, 也可直接执行。自动识别 Linux / WSL / macOS / Windows。
# 配置从 .env 读取 (.env 不存在则报错并提示)。
# =====================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ENV_FILE="$SCRIPT_DIR/.env"

# --- 1. 检测操作系统 ---
detect_os() {
  local u
  u="$(uname -s 2>/dev/null || echo Windows)"
  case "$u" in
    Linux*)   echo "linux" ;;
    Darwin*)  echo "macos" ;;
    MINGW*|CYGWIN*|Windows*) echo "windows" ;;
    *) echo "unknown" ;;
  esac
}

OS=$(detect_os)
echo "[detect] OS: $OS"

# --- 2. 路径处理 ---
case "$OS" in
  linux|macos)
    HOME_DIR="$HOME"
    DOCKER_SOCK="/var/run/docker.sock"
    SHARE_DIR="$HOME"
    ;;
  windows)
    HOME_DIR="${USERPROFILE:-C:/Users/$USERNAME}"
    DOCKER_SOCK="//var/run/docker.sock"
    SHARE_DIR="$HOME_DIR"
    ;;
  *)
    HOME_DIR="$HOME"
    DOCKER_SOCK="/var/run/docker.sock"
    SHARE_DIR="$HOME"
    ;;
esac

MANAGER_DIR="$HOME_DIR/agentteams-manager"
echo "[detect] HOME_DIR     : $HOME_DIR"
echo "[detect] MANAGER_DIR  : $MANAGER_DIR"
echo "[detect] DOCKER_SOCK  : $DOCKER_SOCK"

# --- 3. 检查 .env ---
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "ERROR: $ENV_FILE 不存在"
  echo "       首次使用请执行:"
  echo "         cp $SCRIPT_DIR/.env.example $ENV_FILE"
  echo "         # 编辑 $ENV_FILE 填入真实 LLM API Key 等"
  echo ""
  exit 1
fi

# --- 4. 加载 .env 并构造 docker -e 参数 ---
DOCKER_ENV_ARGS=""
while IFS='=' read -r key value; do
  case "$key" in ''|\#*) continue ;; esac
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  DOCKER_ENV_ARGS="$DOCKER_ENV_ARGS -e $key=$value"
done < "$ENV_FILE"

# --- 5. 检查端口占用 ---
check_port() {
  local port=$1
  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$port "; then
    echo "[warn] 端口 $port 已被占用, 请检查并释放"
  fi
}
for p in 18080 18001 18088 6167; do check_port "$p"; done

# --- 6. 启动容器 ---
echo "[run] 删除旧容器 (如有)"
docker rm -f agentteams-controller 2>/dev/null || true

echo "[run] 启动 agentteams-embedded:latest"
docker run -d --name agentteams-controller \
  --network agentteams-net \
  --network-alias matrix-local.agentteams.io \
  --network-alias aigw-local.agentteams.io \
  --network-alias fs-local.agentteams.io \
  $DOCKER_ENV_ARGS \
  -v "$DOCKER_SOCK:/var/run/docker.sock" \
  --security-opt label=disable \
  -v agentteams-data:/data \
  -v "$MANAGER_DIR:/root/agentteams-fs/agents/manager" \
  -v "$SHARE_DIR:/host-share" \
  -p 18080:8080 -p 18001:8001 -p 18088:8088 -p 6167:6167 \
  --restart unless-stopped \
  higress-registry.cn-hangzhou.cr.aliyuncs.com/agentteams/agentteams-embedded:latest

echo ""
echo "[ok] controller 容器已启动, 等待 ~120s 完成 Manager / Worker bootstrap"
echo "     期间可观察日志:  docker logs -f agentteams-controller"
echo "     就绪标志: ~/agentteams-manager.env 被生成"
