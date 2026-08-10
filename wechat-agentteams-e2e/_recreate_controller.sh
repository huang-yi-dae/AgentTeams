#!/bin/bash
set -e
docker rm -f agentteams-controller 2>/dev/null; true
docker run -d --name agentteams-controller \
  --network agentteams-net \
  --network-alias matrix-local.agentteams.io \
  --network-alias aigw-local.agentteams.io \
  --network-alias fs-local.agentteams.io \
  -e AGENTTEAMS_LANGUAGE=zh \
  -e AGENTTEAMS_LLM_PROVIDER=openai-compat \
  -e AGENTTEAMS_DEFAULT_MODEL=step-3.7-flash \
  -e AGENTTEAMS_LLM_API_KEY="<YOUR_API_KEY>" \
  -e AGENTTEAMS_OPENAI_BASE_URL="https://api.stepfun.com/step_plan/v1" \
  -e AGENTTEAMS_ADMIN_USER=admin \
  -e AGENTTEAMS_ADMIN_PASSWORD=AgentTeams2026 \
  -e AGENTTEAMS_MANAGER_RUNTIME=copaw \
  -e AGENTTEAMS_DEFAULT_WORKER_RUNTIME=copaw \
  -e AGENTTEAMS_MANAGER_ENABLED=true \
  -e AGENTTEAMS_MATRIX_DOMAIN=matrix-local.agentteams.io:18080 \
  -e AGENTTEAMS_MATRIX_URL=http://127.0.0.1:6167 \
  -e AGENTTEAMS_MATRIX_E2EE=0 \
  -e AGENTTEAMS_MATRIX_APPSERVICE_ENABLED=false \
  -e TZ=Asia/Shanghai \
  -v //var/run/docker.sock:/var/run/docker.sock \
  --security-opt label=disable \
  -v agentteams-data:/data \
  -v "C:/Users/$USER/agentteams-manager:/root/agentteams-fs/agents/manager" \
  -v "C:/Users/$USER:/host-share" \
  -p 18080:8080 -p 18001:8001 -p 18088:8088 -p 6167:6167 \
  --restart unless-stopped \
  higress-registry.cn-hangzhou.cr.aliyuncs.com/agentteams/agentteams-embedded:latest
echo "controller created. wait 120s for manager to bootstrap."
