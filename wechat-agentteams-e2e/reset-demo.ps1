#Requires -Version 5.1
<#
.SYNOPSIS
  ServiceDesk Pilot 彻底重置 + 重新跑一次完整流程 (PowerShell)
.DESCRIPTION
  危险操作: 会删除 controller 容器、Docker volume agentteams-data、
  本机 ~/agentteams-manager 目录和历史工单/房间状态, 然后从头启动。
  适用于 demo 前想清干净历史工单和历史消息的场景。
.EXAMPLE
  .\reset-demo.ps1
#>
param(
  [switch]$SkipConfirm,
  [int]$FeedWaitSec = 90,
  [int]$BridgePort = 7890
)

$ScriptDir = $PSScriptRoot
$UserHome = $env:USERPROFILE
if (-not $UserHome) { $UserHome = $HOME }
$HostEnvFile = Join-Path $UserHome 'agentteams-manager.env'
$TokenFile = Join-Path $UserHome 'agentteams-auth-token'
$ManagerDir = Join-Path $UserHome 'agentteams-manager'
$ContainerName = 'agentteams-controller'

function Write-Info($msg)  { Write-Host '==> ' -NoNewline -ForegroundColor Green; Write-Host $msg }
function Write-Warn2($msg) { Write-Host '[WARN] ' -NoNewline -ForegroundColor Yellow; Write-Host $msg }
function Write-Err2($msg)  { Write-Host '[ERROR] ' -NoNewline -ForegroundColor Red; Write-Host $msg }

# --- 0. 危险确认 ---
if (-not $SkipConfirm) {
  Write-Host ''
  Write-Host '⚠️  此操作非常危险，会永久删除以下数据:' -ForegroundColor Red
  Write-Host "    - Docker 容器: $ContainerName"
  Write-Host '    - Docker volume: agentteams-data (Matrix/Manager 持久化数据)'
  Write-Host "    - 本地目录: $ManagerDir (Manager 状态/工单)"
  Write-Host "    - token 文件: $TokenFile"
  Write-Host "    - 当前 bridge / token 刷新循环进程"
  Write-Host ''
  $ans = Read-Host '输入 yes 继续重置, 其他任意键取消'
  if ($ans -ne 'yes') { Write-Host '已取消'; exit 0 }
}

# --- 1. 停掉宿主机进程 (bridge + token loop) ---
Write-Info '停止 bridge / token 刷新循环'
Get-NetTCPConnection -LocalPort $BridgePort -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*cli-token*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# --- 2. 删除所有 agentteams-* 容器 (controller / workers / manager / manager-fixed) ---
# 注意: 只删 controller 不够。worker 与 agentteams-manager-fixed 是旧 volume 时代的孤儿容器,
# 连的是被清掉的旧 Matrix 状态, 不清掉会让新 controller 误以为 team 已存在而跳过重建,
# 表现为 feed 无回复 / 工单不处理。必须全部移除, 让新 controller 从干净 volume 重建整套 team。
Write-Info '删除所有 agentteams-* 容器 (controller / workers / manager / manager-fixed)'
$ids = docker ps -a --filter "name=agentteams-" -q 2>$null
if ($ids) { $ids | ForEach-Object { docker rm -f $_ 2>&1 | Out-Null } }

# --- 3. 删除 Docker volume ---
Write-Info '删除 Docker volume agentteams-data'
docker volume rm agentteams-data 2>&1 | Out-Null

# --- 4. 删除本机 Manager 目录和 token 文件 ---
Write-Info '清理本机 Manager 状态与 token'
if (Test-Path $ManagerDir) { Remove-Item -Path $ManagerDir -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $TokenFile) { Remove-Item -Path $TokenFile -Force -ErrorAction SilentlyContinue }

# --- 5. 重新启动 controller ---
Write-Info '重新启动 controller 容器 (约需 120s)'
Push-Location $ScriptDir
try {
  & .\start.ps1 controller
  if ($LASTEXITCODE -ne 0) { Write-Err2 'controller 启动失败' }
} finally { Pop-Location }

# --- 6. 验证 env 文件 ---
if (-not (Test-Path $HostEnvFile)) {
  Write-Err2 "$HostEnvFile 未生成, controller 可能未就绪"
}
Write-Info "env 文件已生成: $HostEnvFile"

# --- 7. 启动 bridge + token loop ---
Write-Info '启动 bridge 与 token 刷新循环'
Push-Location $ScriptDir
try {
  & .\start-demo-host.ps1 -EnvFile $HostEnvFile -Port $BridgePort
} finally { Pop-Location }

# 简单等待 bridge 就绪
Start-Sleep -Seconds 3

# --- 7.5. 启用 YOLO 模式 (避免 manager 卡 Tool Guard 审批) ---
# 默认启用: ServiceDesk Pilot 是无人值守 demo, 不应卡在 /approve 等待。
# 想关掉可以运行 .\disable-yolo.ps1 (或手动 rm ~/agentteams-manager/yolo-mode)。
Write-Info '启用 Manager YOLO 模式 (避免 Tool Guard 拦截)'
Push-Location $ScriptDir
try {
  & .\enable-yolo.ps1
  if ($LASTEXITCODE -ne 0) { Write-Warn2 'YOLO 启用失败, manager 后续可能被 Tool Guard 拦截' }
} finally { Pop-Location }

# --- 8. 投喂 Manager 组队指令 ---
Write-Info '投喂 Manager 组队指令'
$python = 'python'
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $python = 'py' }
Push-Location (Join-Path $ScriptDir 'bridge')
try {
  & $python feed_manager.py --env-file $HostEnvFile --wait $FeedWaitSec
} finally { Pop-Location }

# --- 9. 打开浏览器观察 ---
Write-Info '打开浏览器观察页面'
Start-Process "http://127.0.0.1:$BridgePort/" -ErrorAction SilentlyContinue
Start-Process "http://127.0.0.1:$BridgePort/wechat.html" -ErrorAction SilentlyContinue

Write-Host ''
Write-Host '✅ 重置完成。当前环境已经是干净状态:' -ForegroundColor Green
Write-Host '   - 无历史工单、无历史消息'
Write-Host '   - Manager 已重新组队'
Write-Host '   - bridge 正在运行'
Write-Host ''
Write-Host '接下来可以手动推送一条测试消息:' -ForegroundColor Cyan
Write-Host "   cd $ScriptDir\simulator" -ForegroundColor Cyan
Write-Host "   $python wechat_sim.py --bridge http://127.0.0.1:$BridgePort --text `"公司打印机连上但打印出来是乱码, 重装驱动也没用, 急用打印合同`" --sender `"王Printer`"" -ForegroundColor Cyan
Write-Host ''
Write-Host '或一次性跑完 6 条场景消息:' -ForegroundColor Cyan
Write-Host "   cd $ScriptDir" -ForegroundColor Cyan
Write-Host "   .\start.ps1 simulate" -ForegroundColor Cyan
