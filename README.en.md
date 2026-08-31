<div align="center">

# AgentBoot

**Minimal, fast, ready-to-run AI Agent launcher**

[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-blue)](#one-command-install)
[![Agents](https://img.shields.io/badge/Agents-15_indigo)](#supported-agents)
[![Model](https://img.shields.io/badge/Default_model-Agnes_free-orange)](#models)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

One command to install, mainstream agents to **choose from a menu** (not a bundle);
a **built-in fallback agent** that always works; **verified slim offline** and **custom-built** packages;
China-network adaptive out of the box. CLI UI in Chinese by default, English switchable.

**Primary entry**: [boot.ide.pub](https://boot.ide.pub) · **Mirror**: [GitHub Pages](https://bit-cook.github.io/AgentBoot/)

**语言 / Language**: [中文 README](README.md) | **English (this file)**

</div>

---

## One-command install

**Linux / macOS**

```bash
curl -fsSL https://boot.ide.pub/install.sh | sh
```

**Windows (PowerShell)**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
```

Two commands after install:

| Command | Purpose |
|---|---|
| `agentboot` | Console menu (install/uninstall agents, models, mirrors, offline builds) — Chinese UI, English switchable via `agentboot lang en` |
| `ab` | Built-in fallback agent — **free Agnes model, zero config** |

> The one-liner installs AgentBoot itself only — which third-party agents to install is always your choice in the menu.

## Features

| | |
|---|---|
| 📦 **Choose what to install** | 15 mainstream agents, multi-select in the menu |
| 🛟 **Built-in fallback agent** | `ab`: zero third-party dependencies, Agnes by default, offline Linux knowledge base, session persistence |
| 🧠 **Model provider manager** | Named custom providers, Ollama/LM Studio presets, failover order, connectivity test |
| 🇨🇳 **China network adaptive** | npmmirror / Node mirrors / Tsinghua PyPI, Worker/Pages/Release fallback, proxy support |
| 📴 **Verified offline packages** | Releases provide Codex and OpenCode slim packs tested through install/run/uninstall; menu `[7]` builds other Agents on their target platform |
| ➕ **Custom agents** | Add anything beyond the registry (npm / pip / script), stored in your home dir |
| 🧹 **Safe uninstall** | Menu `[9]` or `agentboot uninstall <id>`; removes owned program files and preserves user data by default |
| 🔐 **Verified install** | Enforced SHA-256, atomic app switching, rollback; custom scripts require HTTPS and avoid shell interpolation |
| ⚡ **Measured performance** | TLS connection reuse, pre-indexed KB, and an on-device `/bench` for current network/model conditions |

## Supported agents (15)

| # | Agent | Command | Vendor | Offline |
|---|---|---|---|---|
| 1 | CoCo Agent | `coco` | BitCook | Linux/macOS |
| 2 | OpenCode | `opencode` | opencode.ai | ✓ (pinned native binary; x64 baseline fallback) |
| 3 | Hermes Agent | `hermes` | Hermes | ✓ (needs Git) |
| 4 | Cline CLI | `cline` | Cline | ✓ |
| 5 | CodeBuddy CLI | `codebuddy` | Tencent | ✓ |
| 6 | Pi Coding Agent | `pi` | Earendil Works | ✓ |
| 7 | Claude Code | `claude` | Anthropic | ✓ |
| 8 | OpenAI Codex CLI | `codex` | OpenAI | ✓ (Agnes preset) |
| 9 | Qwen Code | `qwen` | Alibaba | ✓ (Agnes preset) |
| 10 | MiMo Code | `mimo` | Xiaomi | ✓ |
| 11 | OpenClaw | `openclaw` | OpenClaw | ✓ |
| 12 | Gemini CLI | `gemini` | Google | ✓ |
| 13 | iFlow CLI | `iflow` | iFlow | ✓ |
| 14 | Aider | `aider` | Aider AI | online only (pip) |
| 15 | Cursor | `cursor` | Anysphere | online only (official signed desktop app in an AgentBoot-owned user directory) |

Package names verified on the npm registry. `✓` = offline payload bundled.

## Built-in fallback agent (ab)

Works when everything else fails — a Python standard-library core shipped with i18n and knowledge-base resources:

```bash
ab                                  # interactive (Agnes free model by default)
ab run "check disk usage"           # one-shot task
ab linux 查看端口占用                # query offline Linux knowledge base
ab doctor                           # environment check
ab bench                            # performance benchmark
ab model                            # provider manager
```

- Tools: run commands (dangerous blocked/confirmed), read/write/edit files, `search_files`, fetch pages
- Offline Linux knowledge base: 9 topics, usage / operations / troubleshooting
- Session persistence (`ab -c`), streaming output, context auto-trimming

## Offline packages

Download a platform-and-Agent-specific verified pack from [Releases](https://github.com/bit-cook/AgentBoot/releases). v1.3.0 verifies OpenCode install, `--version`, and uninstall on Linux, Windows, Intel macOS, and Apple Silicon before uploading packs. Build other Agents on their target platform with menu `[7]` or:

```bash
python core/menu.py build-offline win-x64 claude-code,pi
```

Details: [Installation Guide (EN)](docs/en/install-guide.md) · [安装指南 (中文)](安装指南.md)

## Models

- **Agnes free model** (`agnes-2.5-flash`) built-in — zero config;
- Custom OpenAI-compatible providers (named), local models (Ollama / LM Studio), failover order;
- Config: `~/.agentboot/config.json`; switch language: `agentboot lang en`.

## Uninstall Agents

Open `agentboot` and choose `[9] Uninstall Agents`, or use the CLI:

```bash
agentboot uninstall codex
agentboot uninstall codex,qwen-code       # batch uninstall
agentboot uninstall coco --purge          # also remove CoCo user data
```

AgentBoot records install ownership and will not remove an unrelated command merely because it has the same name. Normal uninstall removes the program, offline payload, and AgentBoot-owned shim while keeping model config, credentials, and sessions. `--purge` currently applies to CoCo and removes its user data as well; AgentBoot does not guess at other projects' data directories. Legacy v1.0.0 installs are removed automatically only when their AgentBoot ownership can be proven.

## Performance (measured via `ab bench`)

`ab bench` measures KB cold/warm queries and first-token latency for a fresh TLS connection versus a reused connection on the current machine and provider. Results vary by network, model, and region and are not a fixed product guarantee.

## Links

- [Installation Guide (EN)](docs/en/install-guide.md) · [安装指南 (中文)](安装指南.md)
- Primary entry: [boot.ide.pub](https://boot.ide.pub) · Mirror: [GitHub Pages](https://bit-cook.github.io/AgentBoot/)

## Security

- The free Agnes model credentials are built in by design; remove `PRESETS["agnes"]["api_key"]` in `core/agent.py` if you fork;
- `smart` inspects every command-chain segment, blocks dangerous operations, and requires interactive confirmation for ordinary mutations; non-interactive runs never silently approve writes;
- `safe` permits read-only commands/tools only. Automation that intentionally mutates the machine must explicitly set `confirm=always`.
- Online tar/zip archives are fetched with same-origin `.sha256` sidecars and verified before an atomic app-directory switch; failed upgrades preserve or restore the previous version.

## License

MIT
