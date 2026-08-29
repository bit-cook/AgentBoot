<div align="center">

# AgentBoot

**极简 · 极速 · 开箱即用的 AI Agent 启动器**

Linux · macOS · Windows ｜ 界面默认中文 ｜ 内置保底 Agent ｜ 中国网络自适应

</div>

---

## 这是什么

AgentBoot 解决一个实际问题：**各种 AI Agent CLI 五花八门、安装方式各异、国内网络动辄失败**。
它把这件事变成两条命令：

```bash
# Linux / macOS：一键安装
curl -fsSL https://boot.ide.pub/install.sh | sh

# Windows（PowerShell）：
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
```

装完得到两个命令：

- **`agentboot`** —— 中文控制台菜单：自选安装各种 Agent、模型配置、镜像与代理设置；
- **`ab`** —— 内置最小 Agent，**开箱即用**（默认 Agnes 免费模型），保底永远可用。

## 特性

- **极简极速**：核心仅两个 Python 文件 + 一个 JSON 注册表，零第三方依赖，启动亚秒级；
- **菜单自选安装**（不是全家桶）：Claude Code、OpenAI Codex、Qwen Code、OpenCode、
  CodeBuddy CLI（腾讯）、MiMo Code（小米）、Cline、Gemini CLI、iFlow CLI、Aider；
- **内置保底 Agent**：当其他 Agent 都装不上时，`ab` 一定能用 —— 默认 Agnes 免费模型，
  支持自定义任意 OpenAI 兼容接口与本地模型（Ollama / LM Studio）；
- **Linux 助手**：`ab` 内置离线 Linux 知识库（9 大主题），可查用法、操作 Linux、修复常见问题；
- **中国网络自适应**：自动探测并切换 npmmirror / Node 镜像 / 清华 PyPI / 多源下载容错 / 代理支持；
- **一键离线安装**：离线包内置各平台 Node 运行时与 Agent 离线载荷，目标机**无需联网、无需解压软件**；
- **跨平台**：Linux / macOS / Windows 同一套体验。

## 快速上手

```bash
agentboot        # 打开控制台菜单
ab               # 直接和内置 Agent 对话
ab run "检查磁盘占用并给出清理建议"     # 一次性任务
ab linux 查看端口占用                    # 直接查离线 Linux 知识库
ab doctor        # 环境体检
```

菜单总览：

```
[1] 环境体检        [2] 在线安装 Agent（多选）    [3] 离线安装 Agent
[4] 模型配置        [5] 镜像与代理设置            [6] 启动内置 Agent
```

## 默认模型（Agnes 免费预设）

| 项 | 值 |
|---|---|
| Base URL | `https://apihub.agnes-ai.com/v1` |
| 模型 ID | `agnes-2.5-flash` |
| 费用 | 永久免费（官方预设） |

切换：`ab` 里输入 `/model`，或菜单 [4]。支持自定义 OpenAI 兼容接口与本地模型。

## 一键离线安装（无网机器）

到 [Releases](https://github.com/bit-cook/AgentBoot/releases) 下载离线包，拷贝到目标机：

```bash
# Linux / macOS（tar 为系统自带）
tar -xzf AgentBoot-offline-v1.0.0.tar.gz && cd AgentBoot && sh install-offline.sh
# 极简环境用自解压单文件：sh AgentBoot-offline-v1.0.0-sfx.sh

# Windows：右键 ZIP 用资源管理器解压（系统自带），然后
powershell -NoProfile -ExecutionPolicy Bypass -File install-offline.ps1
```

**详细步骤、脚本参数、故障排查见根目录《安装指南.md》。**

## 项目结构

```
AgentBoot/
├── install.sh / install.bat / scripts/install.ps1   在线一键安装
├── core/agent.py      内置最小 Agent（单文件零依赖，含工具调用/流式/知识库）
├── core/menu.py       中文控制台菜单（安装器/模型/镜像/离线）
├── agents/registry.json   Agent 注册表（包名已逐一核实）
├── tools/linux-kb/    离线 Linux 知识库（9 主题）
├── scripts/install-offline.* / build-offline.*   离线安装与打包
├── cloudflare/        分发 Worker（boot.ide.pub）与部署说明
├── 安装指南.md        ⭐ 安装/离线部署完整文档
└── README.md
```

## 自建离线包

```bash
sh scripts/build-offline.sh                       # 全量（默认 7 个 Agent × 3 平台）
AGENTS="claude-code,codex" PLATFORMS="linux-x64,win-x64" sh scripts/build-offline.sh
powershell -File scripts\build-offline.ps1        # Windows
```

## 发布分发

- 分发入口：`curl -fsSL https://boot.ide.pub/install.sh | sh`（Cloudflare Worker 免费版，见 `cloudflare/`）
- GitHub Releases：在线包 + 离线包 + 自解压包

## 安全说明

- `core/agent.py` 内置了 Agnes 免费模型的默认接入信息（本项目预设特性）。
  若你 fork 后不希望携带，删除 `PRESETS["agnes"]` 中的 `api_key` 即可；
- 执行命令类工具默认拦截高危操作（格式化、递归删除、重启等），交互模式下需确认。

## License

MIT
