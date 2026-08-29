# =============================================================
#  AgentBoot 在线一键安装（Windows 10/11，兼容 PowerShell 3+）
#  用法（CMD）：
#    powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
#  行为：下载在线包 → 安装到 %LOCALAPPDATA%\AgentBoot → 生成 agentboot / ab 命令
# =============================================================
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Repo      = 'bit-cook/AgentBoot'
$Tag       = 'v1.0.0'
$ZipName   = "agentboot-online-$Tag.zip"
$BootBase  = 'https://boot.ide.pub'
$GH        = "https://github.com/$Repo/releases/download/$Tag"
$LocalRoot = Join-Path $env:LOCALAPPDATA 'AgentBoot'
$AppDir    = Join-Path $LocalRoot 'app'
$BinDir    = Join-Path $LocalRoot 'bin'
$AbRoot    = Join-Path $env:USERPROFILE '.agentboot'

function Write-Ok($m)   { Write-Host "OK $m" -ForegroundColor Green }
function Write-Err($m)  { Write-Host "X  $m" -ForegroundColor Red }
function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

function Get-Url([string]$url, [string]$out) {
    # WebClient 走系统代理（国内友好）；失败再试 Invoke-WebRequest
    try {
        $wc = New-Object Net.WebClient
        $wc.Proxy = [Net.WebRequest]::GetSystemWebProxy()
        $wc.Proxy.Credentials = [Net.CredentialCache]::DefaultCredentials
        $wc.Headers.Add('User-Agent', 'AgentBoot/1.0')
        $wc.DownloadFile($url, $out)
        return $true
    } catch {
        try {
            Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 60 | Out-Null
            return $true
        } catch { return $false }
    }
}

function Expand-Pkg([string]$pkg, [string]$dest) {
    # 优先系统自带 tar（Win10+ 可解 zip），其次 .NET，最后 Shell COM —— 免装解压软件
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) { & $tar -xf $pkg -C $dest; return $true }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($pkg, $dest)
        return $true
    } catch {}
    try {
        $sh = New-Object -ComObject Shell.Application
        $sh.NameSpace($dest).CopyHere($sh.NameSpace($pkg).Items(), 16)
        Start-Sleep -Seconds 3
        return $true
    } catch { return $false }
}

Write-Step "AgentBoot 在线安装 $Tag"

# ---------- 1. 下载（多源容错：Cloudflare → GitHub → 国内加速镜像） ----------
$tmp  = Join-Path $env:TEMP ("agentboot-" + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $tmp, (Join-Path $tmp 'src') -Force | Out-Null
$pkg  = Join-Path $tmp $ZipName
$sources = @(
    "$BootBase/rel/$ZipName",
    "https://bit-cook.github.io/AgentBoot/$ZipName",
    "$GH/$ZipName",
    "https://ghfast.top/$GH/$ZipName",
    "https://gh-proxy.com/$GH/$ZipName"
)
$dl = $false
foreach ($u in $sources) {
    Write-Host "下载：$u"
    $ok = Get-Url $u $pkg
    if ($ok -and (Test-Path $pkg) -and ((Get-Item $pkg).Length -gt 10KB)) { $dl = $true; break }
    Write-Err "该源不可用，尝试下一个 …"
}
if (-not $dl) { Write-Err '所有下载源均失败，请检查网络或改用离线安装包（见《安装指南.md》）'; exit 1 }

# ---------- 2. 解压并安装 ----------
Write-Step '解压安装包'
if (-not (Expand-Pkg $pkg (Join-Path $tmp 'src'))) { Write-Err '解压失败'; exit 1 }
$srcDir = Get-ChildItem (Join-Path $tmp 'src') | Where-Object { $_.PSIsContainer } | Select-Object -First 1
if ($srcDir) { $srcDir = $srcDir.FullName } else { $srcDir = Join-Path $tmp 'src' }

Write-Step "安装程序到 $AppDir"
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
Copy-Item -Path (Join-Path $srcDir '*') -Destination $AppDir -Recurse -Force

# ---------- 3. Python：优先内置便携版（免管理员、够用最快） ----------
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
    $pyDir  = Join-Path $LocalRoot 'runtime\python'
    $pyExe  = Join-Path $pyDir 'python.exe'
    if (-not (Test-Path $pyExe)) {
        $embZip = Join-Path $tmp 'py-embed.zip'
        $embUrls = @(
            'https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip',
            'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
        )
        $got = $false
        foreach ($u in $embUrls) {
            Write-Host "下载便携 Python：$u"
            if (Get-Url $u $embZip) { $got = $true; break }
        }
        if ($got) {
            New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
            Expand-Pkg $embZip $pyDir | Out-Null
        }
    }
    if (Test-Path $pyExe) { Write-Ok "便携 Python 就绪：$pyExe" }
    else {
        Write-Err '自动获取 Python 失败，尝试 winget 安装系统 Python …'
        try { winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements } catch {}
        $pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
} else { Write-Ok "检测到系统 Python：$pyExe" }

# ---------- 4. 命令入口（agentboot / ab） ----------
Write-Step '创建命令：agentboot（控制台） / ab（内置 Agent）'
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
$pyRef = if ($pyExe) { $pyExe } else { 'python' }
$abRootRef = $AbRoot

@"
@echo off
rem AgentBoot 控制台
"$pyRef" "$AppDir\core\menu.py" %*
"@ -replace '\r?\n', "`r`n" | Set-Content -Path (Join-Path $BinDir 'agentboot.cmd') -Encoding ASCII

@"
@echo off
rem AgentBoot 内置最小 Agent
"$pyRef" "$AppDir\core\agent.py" chat %*
"@ -replace '\r?\n', "`r`n" | Set-Content -Path (Join-Path $BinDir 'ab.cmd') -Encoding ASCII
Write-Ok "已写入 $BinDir"

# ---------- 5. PATH 注册（用户级，幂等） ----------
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$add = @($BinDir, (Join-Path $AbRoot 'bin')) | Where-Object { $_ -and ($userPath -notlike "*$_*") }
if ($add) {
    [Environment]::SetEnvironmentVariable('Path', (($add -join ';') + ';' + $userPath), 'User')
    $env:Path = ($add -join ';') + ';' + $env:Path
    Write-Ok '用户 PATH 已更新（新开的终端自动生效）'
}

# ---------- 6. 体检 ----------
Write-Step '环境体检'
if ($pyExe) {
    try { & $pyExe (Join-Path $AppDir 'core\agent.py') doctor } catch { Write-Err '体检脚本执行失败（不影响安装）' }
}

# ---------- 7. 完成 ----------
Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Ok  'AgentBoot 安装完成！'
Write-Host '  控制台菜单 : agentboot'
Write-Host '  内置 Agent : ab      （默认 Agnes 免费模型，直接可用）'
Write-Host '  安装其他 Agent：运行 agentboot → 选 [2] 在线安装'
Write-Host '  当前窗口立即生效：'
Write-Host ('    $env:Path = "' + $BinDir + ';" + $env:Path')
Write-Host '==============================================' -ForegroundColor Cyan
