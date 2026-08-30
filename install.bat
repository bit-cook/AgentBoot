@echo off
rem ============================================================
rem  AgentBoot Windows 一键在线安装（双击运行即可）
rem  实际安装逻辑由 Cloudflare 分发的 install.ps1 完成
rem ============================================================
chcp 65001 >nul
echo.
echo   AgentBoot 在线安装程序（Windows）
echo   --------------------------------
echo   即将下载并安装 AgentBoot 到 %%LOCALAPPDATA%%\AgentBoot
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
set "AB_EXIT=%ERRORLEVEL%"
echo.
echo   如果上方出现错误，请检查网络后重试，或使用离线安装包（见项目《安装指南.md》）。
pause
exit /b %AB_EXIT%
