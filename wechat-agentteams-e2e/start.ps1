#Requires -Version 5.1
<#
.SYNOPSIS
  ServiceDesk Pilot - PowerShell 一键启动入口
.DESCRIPTION
  与 start.sh 等价, 面向 Windows PowerShell 5.1+ 与 PowerShell 7+
  子命令: controller / bridge / feed / viewer / simulate / all / help
#>

param(
  [Parameter(Mandatory=$false, Position=0)]
  [ValidateSet('controller','bridge','feed','viewer','simulate','all','help')]
  [string]$Command = 'help'
)

# --- 路径与常量 ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir '.env'
$ExampleFile = Join-Path $ScriptDir '.env.example'
$userHomePath = $env:USERPROFILE
if (-not $userHomePath) { $userHomePath = $HOME }
$UserHome = $userHomePath
$HostEnvFile = Join-Path $UserHome 'agentteams-manager.env'
$BridgePort = 8770
$ContainerName = 'agentteams-controller'
$Image = 'higress-registry.cn-hangzhou.cr.aliyuncs.com/agentteams/agentteams-embedded:latest'
$GroupRoom = '微信群-IT服务台支持群'

# --- 颜色输出 ---
function Write-Info($msg)  { Write-Host '==> ' -NoNewline -ForegroundColor Green; Write-Host $msg }
function Write-Warn2($msg) { Write-Host '[WARN] ' -NoNewline -ForegroundColor Yellow; Write-Host $msg }
function Write-Err2($msg)  { Write-Host '[ERROR] ' -NoNewline -ForegroundColor Red; Write-Host $msg; exit 1 }

# --- 工具函数 ---
function Get-PythonCmd {
  foreach ($c in 'python','python3','py') {
    if (Get-Command $c -ErrorAction SilentlyContinue) { return $c }
  }
  return $null
}

function Test-PortBusy([int]$Port) {
  try {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    if ($conn) { return $true }
  } catch {
    $found = netstat -ano 2>$null | Select-String (':' + $Port + ' ') | Select-String 'LISTENING'
    if ($found) { return $true }
  }
  return $false
}

# 真正等待 controller + Matrix 就绪: 不仅看 env 文件存在,
# 还要 Matrix API (http://127.0.0.1:6167/_matrix/client/v3/login) 返回 400/401
# 503 表示 Matrix 还没起来, 继续等
function Wait-MatrixReady([int]$MaxWaitSec = 180) {
  Write-Host ('[start] 等待 ~/agentteams-manager.env 生成...')
  $iters = [int]($MaxWaitSec / 2)
  $matrixUrl = 'http://127.0.0.1:6167/_matrix/client/v3/login'
  $matrixReady = $false
  $envReady = $false

  for ($i = 0; $i -lt $iters; $i++) {
    # 检查 env 文件
    if (-not $envReady) {
      if (Test-Path $HostEnvFile) {
        Write-Host ('[ok] ~/agentteams-manager.env 已生成 (' + ($i * 2) + 's)')
        $envReady = $true
      }
    }

    # 检查 Matrix API (从第 30 秒开始检查, 避免过早探测)
    if ($envReady -and -not $matrixReady -and $i -gt 14) {
      try {
        $null = Invoke-WebRequest $matrixUrl `
          -Method POST `
          -ContentType 'application/json' `
          -Body '{}' `
          -UseBasicParsing `
          -TimeoutSec 3 `
          -ErrorAction Stop
        # 200 也算 OK
        $matrixReady = $true
      } catch {
        $resp = $_.Exception.Response
        if ($resp) {
          $code = [int]$resp.StatusCode
          if ($code -eq 400 -or $code -eq 401) {
            # 400/401 = Matrix 服务可用, 拒绝空 body
            $matrixReady = $true
          } elseif ($code -eq 503) {
            # 503 = Matrix 还在启动, 继续等
            $matrixReady = $false
          }
        }
      }
    }

    if ($envReady -and $matrixReady) {
      Write-Host ('[ok] Matrix API 已就绪 (总共 ' + ($i * 2) + 's)') -ForegroundColor Green
      return $true
    }

    Start-Sleep -Seconds 2
  }

  if ($envReady -and -not $matrixReady) {
    Write-Warn2 'env 文件已生成但 Matrix API 仍未就绪 (180s 超时)'
    Write-Warn2 '可手动验证: docker logs agentteams-controller | tail -50'
  } elseif (-not $envReady) {
    Write-Warn2 ('~/agentteams-manager.env 未生成 (' + $MaxWaitSec + 's 超时)')
  }
  return $false
}

# 兼容旧名
function Wait-ManagerEnv([int]$MaxWaitSec = 180) {
  return Wait-MatrixReady $MaxWaitSec
}

# 去掉字符串首尾的引号 (PS 5.1 兼容)
function Remove-Quotes($s) {
  $r = $s.Trim()
  $r = $r -replace '^["'']|["'']$', ''
  return $r
}

# --- 命令实现 ---
function Invoke-Controller {
  if (-not (Test-Path $EnvFile)) {
    Write-Host ''
    Write-Host ('[ERROR] ' + $EnvFile + ' 不存在') -ForegroundColor Red
    Write-Host '  首次使用请执行:'
    Write-Host ('    Copy-Item ' + $ExampleFile + ' ' + $EnvFile)
    Write-Host '  然后编辑填入 AGENTTEAMS_LLM_API_KEY'
    exit 1
  }
  $envContent = Get-Content $EnvFile -Raw
  if ($envContent -match '<replace-with') {
    Write-Host ('[ERROR] ' + $EnvFile + ' 中 AGENTTEAMS_LLM_API_KEY 还是占位符, 请编辑后再跑') -ForegroundColor Red
    exit 1
  }

  Write-Info '启动 controller 容器'
  Write-Host '    端口: 18080 / 18001 / 18088 / 6167'

  foreach ($p in 18080,18001,18088,6167) {
    if (Test-PortBusy $p) { Write-Warn2 ('端口 ' + $p + ' 已被占用') }
  }

  # 解析 .env 为 docker -e 参数
  $envArgs = @()
  Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^(.+?)=(.*)$') {
      $key = $matches[1].Trim()
      $val = Remove-Quotes $matches[2]
      $envArgs += @('-e', ($key + '=' + $val))
    }
  }

  $managerDir = Join-Path $UserHome 'agentteams-manager'

  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err2 '找不到 docker 命令, 请安装 Docker Desktop 并启动'
  }

  Write-Host '[run] 删除旧容器'
  docker rm -f $ContainerName 2>&1 | Out-Null

  Write-Host '[run] 启动镜像'
  $userHomeMount = $UserHome + ':/host-share'
  $managerMount = $managerDir + ':/root/agentteams-fs/agents/manager'
  $dockerArgs = @(
    'run', '-d',
    '--name', $ContainerName,
    '--network', 'agentteams-net',
    '--network-alias', 'matrix-local.agentteams.io',
    '--network-alias', 'aigw-local.agentteams.io',
    '--network-alias', 'fs-local.agentteams.io',
    '-v', '/var/run/docker.sock:/var/run/docker.sock',
    '-v', $userHomeMount,
    '-v', 'agentteams-data:/data',
    '-v', $managerMount,
    '-p', '18080:8080',
    '-p', '18001:8001',
    '-p', '18088:8088',
    '-p', '6167:6167',
    '--security-opt', 'label=disable',
    '--restart', 'unless-stopped'
  )
  $allArgs = $dockerArgs + $envArgs + @($Image)
  & docker $allArgs

  if ($LASTEXITCODE -ne 0) {
    Write-Err2 ('docker run 失败 (exit=' + $LASTEXITCODE + ')')
  }

  Write-Host ''
  Write-Host '[ok] controller 容器已启动, 等待 Manager / Worker bootstrap (~120s)' -ForegroundColor Green
  Write-Host ('     观察日志: docker logs -f ' + $ContainerName)
  Wait-ManagerEnv
}

function Invoke-Bridge {
  Write-Info '启动宿主机桥接服务'
  Write-Host ('    端口: ' + $BridgePort)

  if (Test-PortBusy $BridgePort) {
    Write-Err2 ('端口 ' + $BridgePort + ' 已被占用')
  }
  if (-not (Test-Path $HostEnvFile)) {
    Write-Err2 ($HostEnvFile + ' 不存在. 请先执行: .\start.ps1 controller')
  }

  $python = Get-PythonCmd
  if (-not $python) {
    Write-Err2 '找不到 python / python3 / py, 请安装 Python 3.7+ 并加到 PATH'
  }

  Push-Location (Join-Path $ScriptDir 'bridge')
  try {
    & $python server.py --port $BridgePort --env-file $HostEnvFile --group-room $GroupRoom
  } finally {
    Pop-Location
  }
}

function Invoke-Feed {
  Write-Info '投喂 Manager 组队指令 (DM)'

  if (-not (Test-Path $HostEnvFile)) {
    Write-Err2 ($HostEnvFile + ' 不存在')
  }

  $python = Get-PythonCmd
  if (-not $python) { Write-Err2 '找不到 python' }

  $promptFile = Join-Path $ScriptDir 'prompts\manager-team-prompt.md'

  Push-Location (Join-Path $ScriptDir 'bridge')
  try {
    & $python feed_manager.py --env-file $HostEnvFile --prompt-file $promptFile
  } finally {
    Pop-Location
  }
}

function Invoke-Viewer {
  Write-Info '浏览器打开以下链接'
  Write-Host ''
  Write-Host ('    总览页面:       http://127.0.0.1:' + $BridgePort + '/')
  Write-Host ('    Agent 对话流:   http://127.0.0.1:' + $BridgePort + '/agentflow.html')
  Write-Host ('    模拟微信群:     http://127.0.0.1:' + $BridgePort + '/wechat.html')
  Write-Host ''
  Write-Host '    Higress Console: http://127.0.0.1:18080/'
  Write-Host ''

  Start-Process ('http://127.0.0.1:' + $BridgePort + '/') -ErrorAction SilentlyContinue
}

function Invoke-Simulate {
  Write-Info '推送 6 条模拟微信群消息'
  Write-Host '    间隔: 90s, 场景: 离职账号 / VPN / MFA / 密码 / GitLab / 打印机'

  if (-not (Test-Path $HostEnvFile)) {
    Write-Err2 ($HostEnvFile + ' 不存在')
  }

  try {
    $null = Invoke-WebRequest ('http://127.0.0.1:' + $BridgePort + '/api/status') -UseBasicParsing -TimeoutSec 5
  } catch {
    Write-Err2 'bridge 未运行, 请先执行 .\start.ps1 bridge'
  }

  $python = Get-PythonCmd
  if (-not $python) { Write-Err2 '找不到 python' }

  Push-Location (Join-Path $ScriptDir 'simulator')
  try {
    & $python wechat_sim.py --bridge ('http://127.0.0.1:' + $BridgePort) --interval 90 --env-file $HostEnvFile --group-room $GroupRoom
  } finally {
    Pop-Location
  }
}

function Invoke-All {
  Invoke-Controller

  Write-Host ''
  Write-Host '[next] 请按以下顺序在新 PowerShell 窗口继续:' -ForegroundColor Yellow
  Write-Host ('        cd ' + $ScriptDir)
  Write-Host '        .\start.ps1 bridge' -ForegroundColor Cyan
  Write-Host ''
  Write-Host '        (bridge 起来后)  .\start.ps1 feed' -ForegroundColor Cyan
  Write-Host ''
  Write-Host '        (feed 完成后)    .\start.ps1 viewer' -ForegroundColor Cyan
  Write-Host ''
  Write-Host '        (浏览器打开后)   .\start.ps1 simulate' -ForegroundColor Cyan
}

function Show-Help {
  Write-Host ''
  Write-Host 'ServiceDesk Pilot - PowerShell 一键启动入口' -ForegroundColor Cyan
  Write-Host ''
  Write-Host '用法:'
  Write-Host '  .\start.ps1 <command>'
  Write-Host ''
  Write-Host 'Commands:'
  Write-Host '  controller   步骤 1: 启动 agentteams-embedded 容器 (Docker)'
  Write-Host ('  bridge       步骤 2: 启动宿主机桥接服务 (端口 ' + $BridgePort + ')')
  Write-Host '  viewer       步骤 3: 打印浏览器观察链接 (3 个页面)'
  Write-Host '  simulate     推送 6 条模拟微信群消息 (一次性, 默认间隔 90s)'
  Write-Host '  feed         投喂 Manager 组队指令 (admin -> @manager DM)'
  Write-Host '  all          执行 controller, 然后提示后续步骤'
  Write-Host '  help         显示本帮助'
  Write-Host ''
  Write-Host '依赖:'
  Write-Host '  - Docker Desktop (Windows)'
  Write-Host '  - Python 3.7+ (PATH 中有 python 或 python3)'
  Write-Host ''
  Write-Host '首次使用:'
  Write-Host '  Copy-Item .env.example .env'
  Write-Host '  # 编辑 .env 填入 AGENTTEAMS_LLM_API_KEY 等真实值'
  Write-Host '  .\start.ps1 controller'
  Write-Host ''
  Write-Host '注意: Windows 默认禁止运行未签名脚本, 首次需要:' -ForegroundColor Yellow
  Write-Host '  Set-ExecutionPolicy -Scope Process Bypass' -ForegroundColor Yellow
  Write-Host ''
}

switch ($Command) {
  'controller' { Invoke-Controller }
  'bridge'     { Invoke-Bridge }
  'viewer'     { Invoke-Viewer }
  'simulate'   { Invoke-Simulate }
  'feed'       { Invoke-Feed }
  'all'        { Invoke-All }
  'help'       { Show-Help }
}
