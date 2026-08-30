<div align="center">

# AgentBoot

**极简 · 极速 · 开箱即用的 AI Agent 启动器**

[![平台](https://img.shields.io/badge/平台-Linux%20%7C%20macOS%20%7C%20Windows-blue)](#一键在线安装)
[![Agent](https://img.shields.io/badge/自选_Agent-14_个-indigo)](#支持的-agent)
[![模型](https://img.shields.io/badge/默认模型-Agnes_免费-orange)](#模型开箱即用--完全自定义)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

一条命令装好，主流 Agent **菜单自选**（不是全家桶）；内置**保底 Agent** 永远可用；
提供**已验证精简离线包**与**按需自建离线包**；中国网络环境**开箱自适应**。界面默认中文。

**主入口**：[https://boot.ide.pub](https://boot.ide.pub)　·　**镜像**：[GitHub Pages](https://bit-cook.github.io/AgentBoot/)

**语言 / Language**：中文（本页） | [English](README.en.md)

</div>

---

## 一键在线安装

**Linux / macOS**

```bash
curl -fsSL https://boot.ide.pub/install.sh | sh
```

**Windows（PowerShell）**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
```

装完得到两个命令：

| 命令 | 作用 |
|---|---|
| `agentboot` | 中文控制台菜单：环境体检 / 安装与卸载 Agent / 模型配置 / 镜像代理 / 自定义离线包 |
| `ab` | **内置保底 Agent** —— 默认 Agnes 免费模型，零配置开箱即用 |

> 一键脚本**只装 AgentBoot 本体**，装哪些第三方 Agent 始终由你在菜单里自己决定。

## 特性总览

| | |
|---|---|
| 📦 **菜单自选安装** | 14 个主流 Agent 按需勾选（见下表），支持命令行指定 |
| 🛟 **内置保底 Agent** | `ab` 单文件零依赖：Agnes 开箱即用、离线 Linux 知识库、工具调用、会话持久化 |
| 🧠 **提供商管理器** | Agnes 预设 + 自定义提供商命名管理 + Ollama/LM Studio 本地模型 + 故障切换顺序 |
| 🇨🇳 **中国网络自适应** | npmmirror / Node 镜像 / 清华 PyPI 自动切换；四源下载容错；代理一键配置 |
| 📴 **可验证离线包** | Release 提供经安装/启动/卸载冒烟的 Codex 精简包；菜单 `[7]` 可按目标平台自建其他 Agent 包 |
| ➕ **自定义 Agent** | 菜单向导或 `add-agent` 添加注册表之外的任意 Agent（npm / pip / 脚本），用户目录保存、升级不丢 |
| 🧹 **安全卸载** | 菜单 `[9]` 或 `agentboot uninstall <id>`；精确清理程序，默认保留配置、认证与会话 |
| 🔐 **可验证安装** | 在线包强制 SHA-256 校验、原子切换与失败回滚；自定义脚本仅 HTTPS 且无 shell 拼接 |
| ⚡ **极致性能** | TLS 连接复用、知识库预建索引（热查询 <1ms）、上下文自动瘦身、流式中断保护、`/bench` 基准 |
| 🪟 **三平台一致体验** | 同一套菜单、命令与文档；Windows 长路径与商店存根等细节已处理 |

## 支持的 Agent（14 个）

| # | Agent | 命令 | 厂商 | 离线 | 备注 |
|---|---|---|---|---|---|
| 1 | CoCo Agent | `coco` | BitCook | Linux/macOS | 官方脚本安装 |
| 2 | OpenCode | `opencode` | opencode.ai | ✓ | |
| 3 | Hermes Agent | `hermes` | Hermes | ✓ | 需 Git；国内自动镜像 |
| 4 | Cline CLI | `cline` | Cline | ✓ | |
| 5 | CodeBuddy CLI | `codebuddy` | Tencent | ✓ | |
| 6 | Pi Coding Agent | `pi` | Earendil Works | ✓ | pi.dev 同源包 |
| 7 | Claude Code | `claude` | Anthropic | ✓ | Anthropic 协议，需官方账号 |
| 8 | OpenAI Codex CLI | `codex` | OpenAI | ✓ | **已预置 Agnes**；钉 0.90.0 |
| 9 | Qwen Code | `qwen` | Alibaba | ✓ | **已预置 Agnes** |
| 10 | MiMo Code | `mimo` | Xiaomi | ✓ | |
| 11 | OpenClaw | `openclaw` | OpenClaw | ✓ | |
| 12 | Gemini CLI | `gemini` | Google | ✓ | |
| 13 | iFlow CLI | `iflow` | iFlow 心流 | ✓ | |
| 14 | Aider | `aider` | Aider AI | 仅在线 | pip 生态 |

包名均已逐一在 npm registry 核实；`✓` = 离线包内置完整依赖与运行时。

## 内置保底 Agent（ab）

其他 Agent 都装不上时，`ab` 一定能用——这是 AgentBoot 的设计底线：

- **单文件、零第三方依赖**（仅 Python 标准库），任何有 Python 的机器直接跑；
- **Agnes 免费模型**默认即用；`/model` 管理器可切换自定义接口与本地模型；
- **工具**：执行命令（高危拦截）、读写/精确编辑文件、目录列表、`search_files` 内容搜索、抓网页；
- **离线 Linux 知识库**（9 大主题 60+ 段落）：查用法、操作 Linux、修常见问题（磁盘满/端口占用/服务起不来…）；
- **体验**：流式输出、会话持久化（`ab -c` / `/继续`）、上下文自动瘦身、`/bench` 性能基准。

```bash
ab                                    # 进入交互
ab run "检查磁盘占用并给出清理建议"      # 一次性任务
ab linux 查看端口占用                  # 直接查知识库
ab doctor                             # 环境体检
ab bench                              # 性能基准
```

## 离线安装与瘦身定制

到 [Releases](https://github.com/bit-cook/AgentBoot/releases) 下载带平台与 Agent 名称的已验证精简包，拷到目标机解压后运行包内 `install-offline.ps1` / `sh install-offline.sh`。v1.1.0 首批发布 Linux x64 / Windows x64 的 Codex 包，发布流水线会实际执行安装、`codex --version` 和卸载后才上传。

其他 Agent 使用菜单 `[7]` 或 `build-offline win-x64 claude-code,pi` 在目标平台按需构建。Hermes 含平台相关 Python venv，必须在对应平台构建；Aider 暂不支持离线。

**详细步骤、脚本参数与故障排查见 [《安装指南.md》](安装指南.md)。**

## 模型：开箱即用 + 完全自定义

- **Agnes 免费模型**（`agnes-2.5-flash`）为内置默认——`ab` 零配置直接用；Codex / Qwen 安装后自动接线；
- `/model`（ab）或菜单 `[4]` 打开**提供商管理器**：自定义任意 OpenAI 兼容提供商（命名管理）、Ollama / LM Studio 本地模型、故障切换顺序、连通测试；
- 配置存于 `~/.agentboot/config.json`。

## 卸载 Agent

运行 `agentboot` 选择 `[9] 卸载 Agent`，或直接使用：

```bash
agentboot uninstall codex
agentboot uninstall codex,qwen-code       # 批量卸载
agentboot uninstall coco --purge          # 同时删除 CoCo 用户数据
```

AgentBoot 通过安装清单识别归属，不会因为系统中存在同名命令就误删外部安装。默认卸载只删除程序、离线载荷和 AgentBoot 启动 shim，保留模型配置、认证信息和会话。`--purge` 目前用于 CoCo，可同时清理其用户数据；其他 Agent 的数据目录由各项目定义，AgentBoot 不会猜测删除。旧版遗留安装仅在能证明由 AgentBoot 管理时才会自动卸载。

## 项目结构

```
AgentBoot/
├── install.sh / install.bat / scripts/install.ps1    在线一键安装
├── core/agent.py      内置最小 Agent（单文件零依赖）
├── core/menu.py       中文控制台菜单（安装/模型/镜像/离线/构建）
├── agents/registry.json        Agent 注册表（v2，含平台与依赖声明）
├── tools/linux-kb/    离线 Linux 知识库
├── scripts/           离线安装 / 离线包构建（可定制）/ 工具
├── pages/             GitHub Pages 站点
├── cloudflare/        分发 Worker（boot.ide.pub）
├── 安装指南.md        ⭐ 安装/离线部署完整文档
└── README.md
```

## 性能（`ab bench` 实测）

```
知识库查询   : 冷 2.4 ms（含首载索引） · 热 0.0 ms
模型首字延迟 : 首次（含 TLS 握手）1016 ms · 复用连接 579 ms
连接复用收益 : 每轮省约 437 ms
```

## 文档与链接

- [安装指南](安装指南.md) —— 一键安装 / 离线部署 / 自定义构建 / 模型配置 / 故障排查
- [Releases](https://github.com/bit-cook/AgentBoot/releases) —— 在线包 / 三平台离线包 / 源码包
- 分发入口：[boot.ide.pub](https://boot.ide.pub)（Cloudflare）· [GitHub Pages](https://bit-cook.github.io/AgentBoot/)

## 安全说明

- `core/agent.py` 内置 Agnes 免费模型的默认接入信息（本项目预设特性）；fork 后可删除 `PRESETS["agnes"]` 中的 `api_key`；
- `smart` 策略逐段检查命令链，高危操作（格式化、递归删除、重启等）默认拦截，普通写操作需交互确认；非交互任务不会静默放行写操作；
- `safe` 策略只允许只读命令与工具，自动化确需修改本机时必须显式配置 `confirm=always`。
- 在线 tar/zip 与 `.sha256` 同源下载并强制校验，升级使用原子目录切换，失败自动保留/恢复旧版本。

## License

MIT
