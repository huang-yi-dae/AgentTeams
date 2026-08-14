#Requires -Version 5.1
<#
.SYNOPSIS
  ServiceDesk demo 宿主进程拉起 + 健康检查 (token 刷新循环 + bridge 前端)
.DESCRIPTION
  与 start-demo-host.sh 等价, 面向 Windows PowerShell 5.1 / PowerShell 7
  注意事项:
    - bridge 与 token 循环都是「宿主机进程」, 不在 Docker 内, 会话结束即失联, 需每次冷启动重跑本脚本
    - token 刷新必须用 `docker exec cat` 写文件; 绝不能 `docker cp` 到 bind 挂载文件 (Windows 上静默不生效)
.EXAMPLE
  .\start-demo-host.ps1
  .\start-demo-host.ps1 -EnvFile ~\agentteams-manager.env -Port 7890
#>
param(
  [string]$EnvFile = (Join-Path $env:USERPROFILE 'agentteams-manager.env'),
  [int]$Port = 7890
)

$Controller = 'agentteams-controller'
$TokenFile  = Join-Path $env:USERPROFILE 'agentteams-auth-token'
$ScriptDir  = $PSScriptRoot

Write-Host ('[demo] env=' + $EnvFile + ' port=' + $Port)

# 1) token 刷新循环 (docker exec cat, 不能用 docker cp -> bind 挂载文件静默不生效)
Write-Host '[demo] 1) token 刷新循环 (docker exec cat)'

# 杀掉可能残留的旧循环 (含失效的 docker cp 版本 / 早期手动起的 bash 循环)
# 注意：不限定进程名，只要命令行含 cli-token 都杀，避免多个循环叠加写同一文件
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*cli-token*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$loopFile = Join-Path $env:TEMP 'agentteams-token-loop.ps1'
$loopBody = @"
while (`$true) {
    docker exec $Controller cat /var/run/agentteams/cli-token > '$TokenFile' 2`$null
    Start-Sleep -Seconds 20
}
"@
Set-Content -Path $loopFile -Value $loopBody -Encoding UTF8
Start-Process powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$loopFile) -WindowStyle Hidden
Write-Host ('[demo]    token loop 已启动 (临时脚本: ' + $loopFile + ')')

# 2) bridge 前端 (始终重启, 以加载最新 server.py 代码)
Write-Host '[demo] 2) bridge 前端 (强制重启以加载最新代码)'
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$python = 'python'
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $python = 'py' }
$bridgeDir = Join-Path $ScriptDir 'bridge'
Start-Process $python -ArgumentList @('server.py','--port',$Port,'--env-file',$EnvFile) -WorkingDirectory $bridgeDir -WindowStyle Hidden
Write-Host ('[demo]    bridge 已启动 (端口 ' + $Port + ')')
Start-Sleep -Seconds 4

# 3) 健康检查
Write-Host '[demo] 3) 健康检查'
foreach ($p in @('/','/wechat.html','/agentflow.html','/api/status','/api/events')) {
  $code = 'ERR'
  try {
    $code = (Invoke-WebRequest ('http://localhost:' + $Port + $p) -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop).StatusCode
  } catch {}
  Write-Host ('  ' + $p + ' -> ' + $code)
}

# token 同步校验 (host 文件前 40 字符 vs controller 当前 token)
$tokHost = ''
$tokCtrl = ''
try { $tokHost = (Get-Content $TokenFile -Encoding UTF8 -TotalCount 1 -ErrorAction Stop) } catch {}
try { $tokCtrl = (docker exec $Controller head -c 40 /var/run/agentteams/cli-token 2>$null) } catch {}
if ($tokHost -and $tokCtrl) {
  $a = $tokHost.Substring(0, [Math]::Min(40, $tokHost.Length))
  $b = $tokCtrl.Substring(0, [Math]::Min(40, $tokCtrl.Length))
  if ($a -eq $b) { Write-Host '[demo] token: SYNCED (manager 派单不会 401)' } else { Write-Host '[demo] token: DIFF (警告, manager 可能 401)' }
} else {
  Write-Host '[demo] token: 无法校验'
}

# 4) 启用 Manager YOLO 模式 (避免 demo 跑起来后卡 Tool Guard 审批)
Write-Host '[demo] 4) 启用 Manager YOLO 模式'
Push-Location $ScriptDir
try {
  & .\enable-yolo.ps1
  if ($LASTEXITCODE -ne 0) { Write-Host '[demo]    WARN: YOLO 启用失败 (可手动跑 .\enable-yolo.ps1)' }
} finally { Pop-Location }

Write-Host ('[demo] done. 浏览器: http://localhost:' + $Port + '/  (微信群视图: http://localhost:' + $Port + '/wechat.html)')
