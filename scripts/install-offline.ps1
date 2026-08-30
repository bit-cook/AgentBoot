# =============================================================
#  AgentBoot 离线一键安装（Windows 10/11）
#  前提：已解压 AgentBoot-offline-vX.Y.Z.zip（Windows 资源管理器自带解压，
#        无需安装任何解压软件；Win10+ 也可用系统自带 tar）。
#  本脚本位于离线包根目录。
#
#  用法：
#    右键 install-offline.ps1 →「使用 PowerShell 运行」
#    或 CMD： powershell -NoProfile -ExecutionPolicy Bypass -File install-offline.ps1
#    可选：  -All                  直接安装全部支持离线的 Agent
#            -Agents claude-code,qwen-code   安装指定 Agent
# =============================================================
param(
    [switch]$All,
    [string]$Agents = '',
    [string]$Payload = ''
)
$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Write-Ok($m)   { Write-Host "OK $m" -ForegroundColor Green }
function Write-Err($m)  { Write-Host "X  $m" -ForegroundColor Red }
function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

function Expand-Pkg([string]$pkg, [string]$dest) {
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) { & $tar -xf $pkg -C $dest; return $true }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($pkg, $dest); return $true
    } catch {}
    try {
        $sh = New-Object -ComObject Shell.Application
        $sh.NameSpace($dest).CopyHere($sh.NameSpace($pkg).Items(), 16)
        Start-Sleep -Seconds 3; return $true
    } catch { return $false }
}

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalRoot  = Join-Path $env:LOCALAPPDATA 'AgentBoot'
$AppDir     = Join-Path $LocalRoot 'app'
$BinDir     = Join-Path $LocalRoot 'bin'
$AbRoot     = Join-Path $env:USERPROFILE '.agentboot'

Write-Step 'AgentBoot 离线安装（无需联网）'

# ---------- 1. 校验载荷 ----------
$PayloadDir = if ($Payload) { $Payload } else { Join-Path $ScriptDir 'payloads' }
if (-not (Test-Path (Join-Path $PayloadDir 'agents'))) {
    Write-Err "未找到 payloads/ 离线载荷目录：$PayloadDir"
    Write-Err '请确认脚本位于完整解压后的离线包根目录，或用 -Payload 指定路径。'
    exit 1
}
Write-Ok "离线载荷校验通过：$PayloadDir"

# ---------- 2. 安装程序本体 ----------
Write-Step "安装程序到 $AppDir"
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
foreach ($d in 'core', 'agents', 'tools', 'scripts') {
    if (Test-Path (Join-Path $ScriptDir $d)) {
        Copy-Item (Join-Path $ScriptDir $d) $AppDir -Recurse -Force
    }
}
foreach ($f in 'README.md', '安装指南.md', 'LICENSE', 'CHANGELOG.md', 'install.sh', 'install.bat') {
    if (Test-Path (Join-Path $ScriptDir $f)) { Copy-Item (Join-Path $ScriptDir $f) $AppDir -Force }
}

# ---------- 3. Python：系统优先，否则用离线包内置便携版 ----------
Write-Step '准备 Python 运行时（内置 Agent ab 需要）'
$pyExe = $null
foreach ($c in @((Get-Command python -ErrorAction SilentlyContinue).Source,
                 (Get-Command py -ErrorAction SilentlyContinue).Source)) {
    # 排除 Microsoft Store 的 python 存根：必须能真实执行
    if ($c) {
        try {
            $null = & $c -c "print(1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $pyExe = $c; break }
        } catch { $global:LASTEXITCODE = 0 }
    }
}
if (-not $pyExe) {
    $pyDir = Join-Path $LocalRoot 'runtime\python'
    $pyExe = Join-Path $pyDir 'python.exe'
    if (-not (Test-Path $pyExe)) {
        $emb = Join-Path $PayloadDir 'python\win-embed.zip'
        if (Test-Path $emb) {
            New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
            Expand-Pkg $emb $pyDir | Out-Null
            Write-Ok "已从离线包部署便携 Python"
        } else {
            Write-Err '系统无 Python 且离线包缺少 python/win-embed.zip（ab 将不可用，其他 Agent 不受影响）'
            $pyExe = $null
        }
    }
}
if ($pyExe) { Write-Ok "Python：$pyExe" }

# ---------- 4. 命令入口 ----------
Write-Step '创建命令：agentboot（控制台） / ab（内置 Agent）'
New-Item -ItemType Directory -Path $BinDir, (Join-Path $AbRoot 'bin') -Force | Out-Null
$pyRef = if ($pyExe) { $pyExe } else { 'python' }

@"
@echo off
rem AgentBoot 控制台
"$pyRef" "$AppDir\core\menu.py" %*
"@ -replace '\r?\n', "`r`n" | Set-Content (Join-Path $BinDir 'agentboot.cmd') -Encoding ASCII
@"
@echo off
rem AgentBoot 内置最小 Agent
"$pyRef" "$AppDir\core\agent.py" %*
"@ -replace '\r?\n', "`r`n" | Set-Content (Join-Path $BinDir 'ab.cmd') -Encoding ASCII
Write-Ok "已写入 $BinDir"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$add = @($BinDir, (Join-Path $AbRoot 'bin')) | Where-Object { $_ -and ($userPath -notlike "*$_*") }
if ($add) {
    [Environment]::SetEnvironmentVariable('Path', (($add -join ';') + ';' + $userPath), 'User')
    $env:Path = ($add -join ';') + ';' + $env:Path
    Write-Ok '用户 PATH 已更新（新开的终端自动生效）'
}

# ---------- 5. 离线安装 Agent（载荷直接落盘，不调用 npm） ----------
$env:AGENTBOOT_PAYLOAD = $PayloadDir
$menu = Join-Path $AppDir 'core\menu.py'
if (($All -or $Agents) -and $pyExe) {
    $ids = @()
    if ($All) {
        $ids = (& $pyExe -c "import json,sys;print(' '.join(a['id'] for a in json.load(open(sys.argv[1],encoding='utf-8'))['agents'] if a.get('offline')))" (Join-Path $AppDir 'agents\registry.json')) -split '\s+'
    } else {
        $ids = @($Agents -split ',') | Where-Object { $_ }
    }
    if ($ids) {
        Write-Step "离线安装：$($ids -join ' ')"
        & $pyRef $menu offline --payload $PayloadDir @ids
    }
} elseif (($All -or $Agents) -and -not $pyExe) {
    Write-Err '缺少 Python 运行时，无法执行 Agent 离线安装（控制台菜单功能依赖 Python）'
}

# ---------- 6. 完成 ----------
Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Ok  'AgentBoot 离线安装完成！'
Write-Host '  控制台菜单 : agentboot   （菜单[3] 可继续离线安装其他 Agent）'
Write-Host '  内置 Agent : ab          （默认 Agnes 免费模型；联网后可直接用）'
Write-Host '  纯离线用模型：菜单[4] → 配置本地模型（Ollama / LM Studio）'
Write-Host '==============================================' -ForegroundColor Cyan
if (-not $All -and -not $Agents) {
    if ($pyExe) { & $pyRef (Join-Path $AppDir 'core\menu.py') }
}
