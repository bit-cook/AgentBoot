# =============================================================
#  AgentBoot 离线安装包构建脚本（Windows 构建机）
#  产物（dist/）：
#    AgentBoot-offline-vX.Y.Z.tar.gz / .zip   —— 全平台离线包（含 payloads）
#    AgentBoot-offline-vX.Y.Z-sfx.sh          —— POSIX 自解压安装器
#  说明：
#    - npm 不可用时自动下载便携 Node（npmmirror 镜像）
#    - 跨平台载荷用 npm --os/--cpu 拉取对应二进制
#  用法示例：
#    powershell -File scripts\build-offline.ps1
#    powershell -File scripts\build-offline.ps1 -Platforms linux-x64,win-x64 -Agents claude-code,codex
# =============================================================
param(
    [string]$Tag = '',
    [string]$Platforms = '',
    [string]$Agents = '',
    [string]$NodeVersion = 'v22.23.2'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Root   = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Tag) { $Tag = 'v' + (Get-Content (Join-Path $Root 'VERSION') -Raw).Trim() }
$Dist   = Join-Path $Root 'dist'
$Stage  = Join-Path $Dist "offline\AgentBoot"
$Tar    = Join-Path $env:SystemRoot 'System32\tar.exe'
$HostPlat = 'win-x64'
if (-not $Platforms) { $Platforms = $HostPlat }

function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "OK $m" -ForegroundColor Green }
function Write-Err($m)  { Write-Host "X  $m" -ForegroundColor Red }

function Get-Url([string]$url, [string]$out) {
    Remove-Item $out -Force -ErrorAction SilentlyContinue
    try {
        $wc = New-Object Net.WebClient
        $wc.Proxy = [Net.WebRequest]::GetSystemWebProxy()
        $wc.Proxy.Credentials = [Net.CredentialCache]::DefaultCredentials
        $wc.Headers.Add('User-Agent', 'AgentBoot/1.0')
        $wc.DownloadFile($url, $out)
        if ((Test-Path $out) -and ((Get-Item $out).Length -gt 0)) { return $true }
    } catch {
        Remove-Item $out -Force -ErrorAction SilentlyContinue
    }
    try {
        Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 120 | Out-Null
        if ((Test-Path $out) -and ((Get-Item $out).Length -gt 0)) { return $true }
    } catch {}
    Remove-Item $out -Force -ErrorAction SilentlyContinue
    return $false
}

function Get-Sha256([string]$path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Confirm-NodeArchive([string]$path, [string]$version, [string]$filename) {
    if (-not (Test-Path $path) -or (Get-Item $path).Length -eq 0) { return $false }
    $sums = Join-Path $Dist "SHASUMS256-$version.txt"
    if (-not (Test-Path $sums) -or (Get-Item $sums).Length -eq 0) {
        if (-not (Get-Url "https://nodejs.org/dist/$version/SHASUMS256.txt" $sums)) { return $false }
    }
    $line = Get-Content $sums | Where-Object { $_ -match "\s\*?$([regex]::Escape($filename))$" } | Select-Object -First 1
    if (-not $line) { return $false }
    $expected = ($line -split '\s+')[0].ToLowerInvariant()
    return (Get-Sha256 $path) -eq $expected
}

# 平台映射：node 包名 / npm os / npm cpu / libc
$Map = @{
    'linux-x64'    = @{ file = "node-$NodeVersion-linux-x64.tar.gz";   os = 'linux';  cpu = 'x64';   libc = 'glibc' }
    'linux-arm64'  = @{ file = "node-$NodeVersion-linux-arm64.tar.gz"; os = 'linux';  cpu = 'arm64'; libc = 'glibc' }
    'darwin-x64'   = @{ file = "node-$NodeVersion-darwin-x64.tar.gz";  os = 'darwin'; cpu = 'x64';   libc = $null }
    'darwin-arm64' = @{ file = "node-$NodeVersion-darwin-arm64.tar.gz"; os = 'darwin'; cpu = 'arm64'; libc = $null }
    'win-x64'      = @{ file = "node-$NodeVersion-win-x64.zip";        os = 'win32';  cpu = 'x64';   libc = $null }
}

Write-Step "AgentBoot 离线包构建 $Tag · 平台：$Platforms"

# ---------- 0. 确保 npm 可用 ----------
$npm = (Get-Command npm -ErrorAction SilentlyContinue).Source
if (-not $npm) {
    Write-Step 'npm 不可用，下载便携 Node …'
    $ndir = Join-Path $Dist 'build-node'
    $nzip = Join-Path $Dist 'node-portable.zip'
    New-Item -ItemType Directory -Path $ndir -Force | Out-Null
    $nfile = "node-$NodeVersion-win-x64.zip"
    if (-not (Get-Url "https://registry.npmmirror.com/-/binary/node/$NodeVersion/$nfile" $nzip) -or
        -not (Confirm-NodeArchive $nzip $NodeVersion $nfile)) {
        if (-not (Get-Url "https://nodejs.org/dist/$NodeVersion/$nfile" $nzip) -or
            -not (Confirm-NodeArchive $nzip $NodeVersion $nfile)) { throw "Node 下载或 SHA-256 校验失败：$nfile" }
    }
    & $Tar -xf $nzip -C $ndir
    Remove-Item $nzip -Force
    $inner = Get-ChildItem $ndir | Where-Object { $_.PSIsContainer } | Select-Object -First 1
    $env:Path = "$($inner.FullName);$env:Path"
    $npm = Join-Path $inner.FullName 'npm.cmd'
}
Write-Ok "npm：$npm"

# ---------- 1. 复制项目到暂存区 ----------
Write-Step '复制项目文件 …'
if (Test-Path $Stage) {
    # 载荷里有超长路径（如 cline 的深层 node_modules），Remove-Item 不支持，用 robocopy /MIR 清空
    $emptyDir = Join-Path $Dist 'empty-dir'
    New-Item -ItemType Directory -Path $emptyDir -Force | Out-Null
    robocopy $emptyDir $Stage /MIR /NFL /NDL /NJH /NJS | Out-Null
    Remove-Item $emptyDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
& python (Join-Path $Root 'scripts\tools\stage_application.py') $Root $Stage
if ($LASTEXITCODE -ne 0) { throw '复制应用显式清单失败' }

# ---------- 2. 下载各平台 Node 运行时 ----------
New-Item -ItemType Directory -Path (Join-Path $Stage 'payloads\node') -Force | Out-Null
foreach ($plat in $Platforms -split ',') {
    $m = $Map[$plat.Trim()]
    if (-not $m) { Write-Err "未知平台：$plat"; exit 1 }
    Write-Step "Node 运行时 [$plat] …"
    $arc = Join-Path $Dist $m.file
    if (-not (Confirm-NodeArchive $arc $NodeVersion $m.file)) {
        Remove-Item $arc -Force -ErrorAction SilentlyContinue
        if (-not (Get-Url "https://registry.npmmirror.com/-/binary/node/$NodeVersion/$($m.file)" $arc)) {
            if (-not (Get-Url "https://nodejs.org/dist/$NodeVersion/$($m.file)" $arc)) {
                Write-Err "下载失败：$($m.file)"; exit 1
            }
        }
        if (-not (Confirm-NodeArchive $arc $NodeVersion $m.file)) { throw "Node SHA-256 校验失败：$($m.file)" }
    }
    $tmpEx = Join-Path $Dist ("extract-" + [guid]::NewGuid().ToString('N').Substring(0, 6))
    New-Item -ItemType Directory -Path $tmpEx -Force | Out-Null
    & $Tar -xf $arc -C $tmpEx
    $inner = Get-ChildItem $tmpEx | Where-Object { $_.PSIsContainer } | Select-Object -First 1
    $dest = Join-Path $Stage "payloads\node\$plat"
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Move-Item $inner.FullName $dest
    Remove-Item $tmpEx -Recurse -Force
    Write-Ok "Node [$plat] 就绪"
}

# ---------- 3. 逐 Agent × 平台 安装离线载荷 ----------
$registry = Get-Content (Join-Path $Root 'agents\registry.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$want = if ($Agents) { $Agents -split ',' } else {
    @($registry.agents | Where-Object { $_.offline -and (-not $_.os -or $_.os -contains 'windows') } |
      ForEach-Object { $_.id })
}
foreach ($a in $registry.agents) {
    if ($want -notcontains $a.id -or $a.method -ne 'npm') { continue }
    foreach ($plat in $Platforms -split ',') {
        $m = $Map[$plat.Trim()]
        $prefix = Join-Path $Stage "payloads\agents\$($a.id)\$plat"
        New-Item -ItemType Directory -Path $prefix -Force | Out-Null
        Write-Step "载荷 $($a.id) [$plat] ← $($a.npm)"
        $extra = @()
        if ($m.libc) { $extra += @('--libc', $m.libc) }
        if ($a.npm_install_flags) { $extra += @($a.npm_install_flags) }
        & $npm install --global-style --prefix $prefix --os $m.os --cpu $m.cpu @extra `
            $a.npm --registry https://registry.npmmirror.com --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $prefix 'node_modules'))) {
            Write-Err "载荷安装失败：$($a.id)@$plat（继续其他载荷）"
        } else { Write-Ok "$($a.id) [$plat] 完成" }
        $global:LASTEXITCODE = 0

        # hermes 特殊：完整运行时（uv 预置 + postinstall），并写 PACK_ROOT 供离线安装时修复 venv 路径
        if ($a.id -eq 'hermes' -and (Test-Path (Join-Path $prefix 'node_modules\hermes-agent'))) {
            if ($plat -ne $HostPlat) {
                Write-Err "Hermes 完整运行时必须在目标平台构建：当前 $HostPlat，目标 $plat；已移除半成品载荷"
                Remove-Item $prefix -Recurse -Force -ErrorAction SilentlyContinue
                continue
            }
            $pkg = Join-Path $prefix 'node_modules\hermes-agent'
            & python (Join-Path $Root 'scripts\tools\seed_uv_generic.py') $pkg $plat
            $env:GIT_CONFIG_COUNT = '1'
            $env:GIT_CONFIG_KEY_0 = 'url.https://gh-proxy.com/https://github.com/.insteadOf'
            $env:GIT_CONFIG_VALUE_0 = 'https://github.com/'
            $env:UV_PYTHON_INSTALL_MIRROR = 'https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download'
            $env:UV_HTTP_TIMEOUT = '300'
            & node (Join-Path $pkg 'scripts\postinstall.js')
            [IO.File]::WriteAllText((Join-Path $prefix 'PACK_ROOT.txt'), $pkg)
            $env:GIT_CONFIG_COUNT = $null; $env:GIT_CONFIG_KEY_0 = $null; $env:GIT_CONFIG_VALUE_0 = $null
            Write-Ok "hermes 完整运行时就绪 [$plat]"
        }
        $global:LASTEXITCODE = 0
    }
}

# ---------- 4. 内置 Python（Windows 便携版）+ CoCo 离线载荷 ----------
Write-Step '内置 Python（win-embed）…'
$pyDir = Join-Path $Stage 'payloads\python'
New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
$pyZip = Join-Path $pyDir 'win-embed.zip'
if (-not (Test-Path $pyZip)) {
    if (-not (Get-Url 'https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip' $pyZip)) {
        Get-Url 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' $pyZip | Out-Null
    }
}
if ((Get-Sha256 $pyZip) -ne '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3') {
    Remove-Item $pyZip -Force -ErrorAction SilentlyContinue
    throw 'Windows Python 便携包 SHA-256 校验失败'
}
Write-Ok 'win-embed.zip 就绪'

# CoCo（script 类）离线载荷：发行包 + sha256 + Agnes 密钥 + Node 22.23 运行时
$wantCoco = ($want -contains 'coco')
if ($wantCoco) {
    $CocoVer = '0.8.0'
    foreach ($plat in ($Platforms -split ',')) {
        if ($plat -eq 'win-x64') { continue }   # CoCo 官方不支持 Windows
        $cdir = Join-Path $Stage "payloads\agents\coco\$plat"
        New-Item -ItemType Directory -Path $cdir -Force | Out-Null
        $files = @(
            @("https://gh-proxy.com/https://github.com/bit-cook/coco/releases/download/v$CocoVer/coco-$CocoVer.tgz", "coco-$CocoVer.tgz"),
            @("https://gh-proxy.com/https://github.com/bit-cook/coco/releases/download/v$CocoVer/coco-$CocoVer.tgz.sha256", "coco-$CocoVer.tgz.sha256"),
            @("https://gh-proxy.com/https://github.com/bit-cook/coco/releases/download/installer-v0.1.1.1/agnes.key", "agnes.key")
        )
        foreach ($f in $files) {
            $dest = Join-Path $cdir $f[1]
            if (-not (Test-Path $dest)) {
                if (-not (Get-Url $f[0] $dest)) { Write-Err "CoCo 载荷下载失败：$($f[1])" }
            }
        }
        $nf = switch ($plat) {
            'linux-x64'    { 'node-v22.23.2-linux-x64.tar.gz' }
            'linux-arm64'  { 'node-v22.23.2-linux-arm64.tar.gz' }
            'darwin-x64'   { 'node-v22.23.2-darwin-x64.tar.gz' }
            'darwin-arm64' { 'node-v22.23.2-darwin-arm64.tar.gz' }
        }
        $ndest = Join-Path $cdir $nf
        if (-not (Confirm-NodeArchive $ndest 'v22.23.2' $nf)) {
            Remove-Item $ndest -Force -ErrorAction SilentlyContinue
            if (-not (Get-Url "https://registry.npmmirror.com/-/binary/node/v22.23.2/$nf" $ndest)) {
                Get-Url "https://nodejs.org/dist/v22.23.2/$nf" $ndest | Out-Null
            }
            if (-not (Confirm-NodeArchive $ndest 'v22.23.2' $nf)) { throw "CoCo Node SHA-256 校验失败：$nf" }
        }
        Write-Ok "CoCo 离线载荷 [$plat] 就绪"
    }
}

# ---------- 5. 离线安装脚本复制到包根目录 + 清单 ----------
& python (Join-Path $Root 'scripts\tools\validate_offline_payload.py') $Stage $Platforms ($want -join ',')
if ($LASTEXITCODE -ne 0) { throw '离线载荷闭包校验失败，拒绝打包' }
Copy-Item (Join-Path $Root 'scripts\install-offline.sh')  $Stage -Force
Copy-Item (Join-Path $Root 'scripts\install-offline.ps1') $Stage -Force
$manifest = @()
$manifest += "AgentBoot Offline Bundle"
$manifest += "version   : $Tag"
$manifest += "built     : $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
$manifest += "node      : $NodeVersion"
$manifest += "platforms : $Platforms"
$manifest += "agents    : $($want -join ', ')"
$manifest += "python    : 3.12.10 embed (windows)"
$manifest += ""
$manifest += "用法见《安装指南.md》：解压后运行 install-offline.sh / install-offline.ps1"
$manifest | Set-Content (Join-Path $Stage 'MANIFEST.txt') -Encoding UTF8

# ---------- 6. 按平台打包（每台目标机只需自己平台的包） ----------
Write-Step '按平台打包 …'
$plats = $Platforms -split ','
foreach ($plat in $plats) {
    & python (Join-Path $Root 'scripts\tools\hash_tree.py') (Join-Path $Stage 'payloads') (Join-Path $Stage 'PAYLOAD_SHA256SUMS.txt') $plat
    if ($LASTEXITCODE -ne 0) { throw "生成 $plat 离线载荷哈希清单失败" }
    $ex = @()
    foreach ($other in $plats) {
        if ($other -ne $plat) {
            $ex += @('--exclude', "AgentBoot/payloads/agents/*/$other",
                     '--exclude', "AgentBoot/payloads/node/$other")
        }
    }
    if ($plat -ne 'win-x64') { $ex += @('--exclude', 'AgentBoot/payloads/python') }
    Push-Location (Join-Path $Dist 'offline')
    try {
        if ($plat -eq 'win-x64') {
            $out = Join-Path $Dist "AgentBoot-offline-$Tag-$plat.zip"
            if (Test-Path $out) { Remove-Item $out -Force }
            & $Tar -a -cf $out $ex AgentBoot
        } else {
            $out = Join-Path $Dist "AgentBoot-offline-$Tag-$plat.tar.gz"
            if (Test-Path $out) { Remove-Item $out -Force }
            & $Tar -czf $out $ex AgentBoot
        }
        Write-Ok ("{0}  {1:N0} MB" -f (Split-Path $out -Leaf), ((Get-Item $out).Length / 1MB))
    } finally { Pop-Location }
}

# ---------- 7. POSIX 自解压安装器（非 Windows 平台） ----------
$pyB = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($pyB) {
    foreach ($plat in ($plats | Where-Object { $_ -ne 'win-x64' })) {
        $gz = Join-Path $Dist "AgentBoot-offline-$Tag-$plat.tar.gz"
        if (-not (Test-Path $gz)) { continue }
        Write-Step "生成自解压安装器 [$plat] …"
        $sfx = Join-Path $Dist "AgentBoot-offline-$Tag-$plat-sfx.sh"
        $header = @'
#!/bin/sh
# AgentBoot 离线自解压安装器：目标机器无需任何解压软件，直接运行
#   sh AgentBoot-offline-vX.Y.Z-<平台>-sfx.sh
set -eu
SKIP=$(awk '/^__AGENTBOOT_PAYLOAD_BELOW__$/{print NR+1; exit}' "$0")
tmp="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-sfx-$$)"
mkdir -p "$tmp"
echo "==> AgentBoot 离线自解压安装：解压中，请稍候 …"
tail -n +"$SKIP" "$0" | { base64 -d 2>/dev/null || base64 -D 2>/dev/null || openssl base64 -d -A; } | tar -xzf - -C "$tmp"
exec sh "$tmp/AgentBoot/install-offline.sh" "$@"
__AGENTBOOT_PAYLOAD_BELOW__
'@
        [IO.File]::WriteAllText($sfx, ($header -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
        & $pyB (Join-Path $Root 'scripts\tools\sfx_append.py') $gz $sfx
        Write-Ok ("sfx.sh [{0}]：{1:N0} MB" -f $plat, ((Get-Item $sfx).Length / 1MB))
    }
} else {
    Write-Err '本机无 python，跳过自解压包生成（可在 POSIX 上用 build-offline.sh 生成）'
}

Write-Step '构建完成'
Get-ChildItem $Dist -File | ForEach-Object { Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
