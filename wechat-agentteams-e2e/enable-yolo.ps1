#Requires -Version 5.1
<#
.SYNOPSIS
  为 ServiceDesk Pilot Manager 启用 YOLO 模式 (PowerShell)
.DESCRIPTION
  YOLO 模式 = Manager Agent 在 admin 不可达的情况下自动决策、不再卡审批等待。
  这是 ServiceDesk Pilot 比赛 demo 的标准配置 —— 评审不会在 Element 客户端帮你点 /approve。

  原理:
    manager/scripts/init/start-manager-agent.sh 第 48 行会检查
      [ -z "${AGENTTEAMS_YOLO:-}" ] && [ -f /root/manager-workspace/yolo-mode ]
    文件存在即等价于 AGENTTEAMS_YOLO=1, Manager 自动决策不再阻塞。

  重要边界:
    - 这个文件只在 Manager 容器 NEXT START 时生效;
      已经在跑且卡在 Tool Guard 审批提示里的 Manager 进程,
      不会因为新文件而自动恢复 —— 那个状态是进程内的, 必须用 Element 客户端
      跟 Manager 说一句话唤醒它, 它重新执行 turn 时就不会再走 Tool Guard 拦截路径了。
    - 如果 manager 容器还没起, 脚本会先把 marker 写到 host 的 ~/agentteams-manager/yolo-mode,
      等下次 reset / 重启 controller 时, 容器挂载 /root/manager-workspace 会自动看到这个文件。

.EXAMPLE
  .\enable-yolo.ps1
  .\enable-yolo.ps1 -ContainerName agentteams-manager-fixed
#>
param(
  [string]$ContainerName = 'agentteams-manager',
  [string]$HostMarkerDir = (Join-Path $env:USERPROFILE 'agentteams-manager')
)

function Write-Info($msg)  { Write-Host '==> ' -NoNewline -ForegroundColor Green; Write-Host $msg }
function Write-Warn2($msg) { Write-Host '[WARN] ' -NoNewline -ForegroundColor Yellow; Write-Host $msg }
function Write-Err2($msg)  { Write-Host '[ERROR] ' -NoNewline -ForegroundColor Red; Write-Host $msg }

$InsideMarker = '/root/manager-workspace/yolo-mode'
$HostMarker    = Join-Path $HostMarkerDir 'yolo-mode'

# --- 0. 检测容器是否在跑 ---
$running = $false
try {
  $state = (docker inspect -f '{{.State.Running}}' $ContainerName 2>$null) 2>$null
  if ($LASTEXITCODE -eq 0 -and $state -eq 'true') { $running = $true }
} catch {}

if ($running) {
  Write-Info "manager 容器 '$ContainerName' 已在跑, 写入容器内 marker"
  docker exec $ContainerName sh -c "touch $InsideMarker && ls -la $InsideMarker" 2>&1 | Out-Null
  $rc = $LASTEXITCODE
  if ($rc -ne 0) {
    Write-Err2 "docker exec touch 失败 (rc=$rc), 检查容器是否真的在跑 / 名字是否正确"
    exit 1
  }
  Write-Info "已写入 $InsideMarker (Manager 下次启动自动走 YOLO)"
} else {
  Write-Warn2 "manager 容器 '$ContainerName' 当前未运行"
  Write-Info "改写到 host 临时目录, 等下次 reset / 重启 controller 时容器会自动看到"
  if (-not (Test-Path $HostMarkerDir)) {
    New-Item -ItemType Directory -Path $HostMarkerDir -Force | Out-Null
  }
  # 空文件即可, start-manager-agent.sh 只看 [ -f ... ]
  [IO.File]::WriteAllBytes($HostMarker, @())
  Write-Info "已写入 $HostMarker"
}

# --- 1. 提示用户 ---
Write-Host ''
Write-Host '下一步:' -ForegroundColor Cyan
if ($running) {
  Write-Host '  1. 已经在 Element Web 里 manager DM 房间发一条任意消息给它 (例如 "继续")' -ForegroundColor Cyan
  Write-Host '     —— 唤醒 Manager, 它重新跑 turn 时就不会再被 Tool Guard 拦截了' -ForegroundColor Cyan
  Write-Host '  2. 之后跑 .\reset-demo.ps1 重置环境时, 这个 marker 会自动保留' -ForegroundColor Cyan
} else {
  Write-Host '  1. 现在跑 .\reset-demo.ps1 让 controller 重建 manager 容器' -ForegroundColor Cyan
  Write-Host '  2. Manager 启动时会自动检测 yolo-mode, 直接进入全自动模式' -ForegroundColor Cyan
}
Write-Host ''
Write-Host '关闭 YOLO (回归审批模式):' -ForegroundColor DarkGray
if ($running) {
  Write-Host "  docker exec $ContainerName rm -f $InsideMarker" -ForegroundColor DarkGray
}
Write-Host "  Remove-Item -Force '$HostMarker'" -ForegroundColor DarkGray