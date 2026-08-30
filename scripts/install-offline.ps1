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

function Get-Sha256([string]$path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Expand-Pkg([string]$pkg, [string]$dest) {
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) {
        & $tar -xf $pkg -C $dest
        if ($LASTEXITCODE -eq 0 -and (Get-ChildItem $dest -Force | Select-Object -First 1)) { return $true }
        $global:LASTEXITCODE = 0
    }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($pkg, $dest); return $true
    } catch {}
    try {
        $sh = New-Object -ComObject Shell.Application
        $sh.NameSpace($dest).CopyHere($sh.NameSpace($pkg).Items(), 16)
        for ($i = 0; $i -lt 30; $i++) {
            if (Get-ChildItem $dest -Force | Select-Object -First 1) { return $true }
            Start-Sleep -Milliseconds 500
        }
        return $false
    } catch { return $false }
}

function Assert-ManagedLauncher([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    $item = Get-Item -LiteralPath $path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "拒绝覆盖重解析点命令：$path"
    }
    if (-not (Select-String -LiteralPath $path -Pattern '^rem AgentBoot ' -Quiet)) {
        throw "拒绝覆盖不属于 AgentBoot 的命令：$path"
    }
}

function Set-LauncherAtomic([string]$path, [string]$content) {
    $tmp = "$path.new.$([guid]::NewGuid().ToString('N').Substring(0,8))"
    try {
        $content -replace '\r?\n', "`r`n" | Set-Content -LiteralPath $tmp -Encoding ASCII
        Move-Item -LiteralPath $tmp -Destination $path -Force
    } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

function Restore-AppAtomic {
    if ($script:PendingApp -and (Test-Path $script:PendingApp)) {
        Remove-Item $script:PendingApp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($script:PendingOldApp -and (Test-Path $script:PendingOldApp)) {
        Move-Item $script:PendingOldApp $script:PendingApp
    }
    $script:PendingOldApp = $null; $script:PendingApp = $null
}
function Complete-AppAtomic {
    if ($script:PendingOldApp -and (Test-Path $script:PendingOldApp)) { Remove-Item $script:PendingOldApp -Recurse -Force }
    $script:PendingOldApp = $null; $script:PendingApp = $null
}
$script:PendingOldApp = $null; $script:PendingApp = $null
trap { Restore-AppAtomic; Write-Error $_; exit 1 }

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalRoot  = Join-Path $env:LOCALAPPDATA 'AgentBoot'
$AppDir     = Join-Path $LocalRoot 'app'
$BinDir     = Join-Path $LocalRoot 'bin'
$AbRoot     = Join-Path $env:USERPROFILE '.agentboot'

Write-Step 'AgentBoot 离线安装（无需联网）'

$launchers = @((Join-Path $BinDir 'agentboot.cmd'), (Join-Path $BinDir 'ab.cmd'))
foreach ($launcher in $launchers) {
    Assert-ManagedLauncher $launcher
}

# ---------- 1. 校验载荷 ----------
$PayloadDir = if ($Payload) { $Payload } else { Join-Path $ScriptDir 'payloads' }
if (-not (Test-Path (Join-Path $PayloadDir 'agents'))) {
    Write-Err "未找到 payloads/ 离线载荷目录：$PayloadDir"
    Write-Err '请确认脚本位于完整解压后的离线包根目录，或用 -Payload 指定路径。'
    exit 1
}
$sums = Join-Path $ScriptDir 'PAYLOAD_SHA256SUMS.txt'
if (-not (Test-Path $sums)) { throw '缺少 PAYLOAD_SHA256SUMS.txt，拒绝安装未验证载荷' }
foreach ($line in Get-Content $sums) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split '\s+', 2
    $file = Join-Path $ScriptDir $parts[1].Replace('/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $file)) { throw "载荷缺失：$($parts[1])" }
    if ((Get-Sha256 $file) -ne $parts[0].ToLowerInvariant()) {
        throw "载荷 SHA-256 校验失败：$($parts[1])"
    }
}
Write-Ok "离线载荷 SHA-256 校验通过：$PayloadDir"

# ---------- 2. 安装程序本体 ----------
Write-Step "安装程序到 $AppDir"
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
$newApp = "$AppDir.new.$suffix"
$oldApp = "$AppDir.old.$suffix"
New-Item -ItemType Directory -Path $newApp -Force | Out-Null
foreach ($d in 'core', 'agents', 'tools', 'scripts') {
    if (Test-Path (Join-Path $ScriptDir $d)) {
        Copy-Item (Join-Path $ScriptDir $d) $newApp -Recurse -Force
    }
}
foreach ($f in 'VERSION', 'README.md', '安装指南.md', 'LICENSE', 'CHANGELOG.md', 'install.sh', 'install.bat') {
    if (Test-Path (Join-Path $ScriptDir $f)) { Copy-Item (Join-Path $ScriptDir $f) $newApp -Force }
}
if (-not (Test-Path (Join-Path $newApp 'core\menu.py')) -or -not (Test-Path (Join-Path $newApp 'core\agent.py'))) {
    Remove-Item $newApp -Recurse -Force -ErrorAction SilentlyContinue; throw '离线包结构无效'
}
if (Test-Path $AppDir) { Move-Item $AppDir $oldApp }
try {
    Move-Item $newApp $AppDir
    $script:PendingOldApp = if (Test-Path $oldApp) { $oldApp } else { $null }
    $script:PendingApp = $AppDir
}
catch { if (Test-Path $oldApp) { Move-Item $oldApp $AppDir }; throw }

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
$pyCommand = if ($pyExe -and ([IO.Path]::GetFileName($pyExe) -like 'py*')) { 'py' } else { 'python' }
$agentbootLauncher = @"
@echo off
rem AgentBoot 控制台
set "AB_INSTALL=%~dp0.."
set "PYTHON=$pyCommand"
if exist "%AB_INSTALL%\runtime\python\python.exe" set "PYTHON=%AB_INSTALL%\runtime\python\python.exe"
"%PYTHON%" "%AB_INSTALL%\app\core\menu.py" %*
"@
$abLauncher = @"
@echo off
rem AgentBoot 内置最小 Agent
set "AB_INSTALL=%~dp0.."
set "PYTHON=$pyCommand"
if exist "%AB_INSTALL%\runtime\python\python.exe" set "PYTHON=%AB_INSTALL%\runtime\python\python.exe"
"%PYTHON%" "%AB_INSTALL%\app\core\agent.py" %*
"@
Set-LauncherAtomic (Join-Path $BinDir 'agentboot.cmd') $agentbootLauncher
Set-LauncherAtomic (Join-Path $BinDir 'ab.cmd') $abLauncher
Complete-AppAtomic
Write-Ok "已写入 $BinDir"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathItems = @($userPath -split ';' | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') })
$add = @($BinDir, (Join-Path $AbRoot 'bin')) | Where-Object {
    $candidate = $_.TrimEnd('\')
    $_ -and -not ($pathItems | Where-Object { [string]::Equals($_, $candidate, [StringComparison]::OrdinalIgnoreCase) })
}
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
        $manifest = Get-Content (Join-Path $ScriptDir 'MANIFEST.txt') | Where-Object { $_ -match '^agents\s*:' } | Select-Object -First 1
        if (-not $manifest) { throw 'MANIFEST.txt 未列出 Agent' }
        $packed = (($manifest -split ':', 2)[1]).Trim()
        $ids = @($packed -split ',\s*' | Where-Object { $_ })
    } else {
        $ids = @($Agents -split ',' | Where-Object { $_ })
    }
    if ($ids) {
        Write-Step "离线安装：$($ids -join ' ')"
        $menuArgs = @($menu, 'offline', '--payload', $PayloadDir) + @($ids)
        & $pyExe @menuArgs
        if ($LASTEXITCODE -ne 0) { throw "Agent 离线安装失败（exit=$LASTEXITCODE）" }
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
    if ($pyExe) { & $pyExe (Join-Path $AppDir 'core\menu.py') }
}
