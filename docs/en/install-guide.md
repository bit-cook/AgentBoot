# AgentBoot Installation Guide

> **v1.1.0** · Linux / macOS / Windows · CLI UI in Chinese by default (switchable to English: `agentboot lang en`)
> AgentBoot is a minimal, fast, ready-to-run AI Agent launcher: it ships a built-in fallback agent (free **Agnes** model by default), while the other agents (Claude Code, Codex, Qwen Code, OpenCode, CodeBuddy, MiMo Code, Cline, Pi, CoCo, …) are installed **from a menu of your choice**.

**目录 / Table of contents**: [One-command online install](#one-command-online-install) · [One-command offline install](#one-command-offline-install) · [Custom agents](#custom-agents-beyond-the-registry) · [Custom offline packages](#custom-offline-packages-slim) · [China network](#china-network-adaptive) · [Model providers](#model-providers) · [Built-in agent](#built-in-agent-ab) · [Upgrade & uninstall](#upgrade--uninstall) · [Troubleshooting](#online-install-troubleshooting) · [FAQ](#faq)

---

## ⚡ One-command online install (recommended)

**Linux / macOS**

```bash
curl -fsSL https://boot.ide.pub/install.sh | sh
```

**Windows (PowerShell / CMD)**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"
```

**Fallback entries** — the installer tries these sources in order automatically (no manual action needed): `boot.ide.pub` (Cloudflare) → GitHub Pages → GitHub Releases → China accelerators (`ghfast.top`, `gh-proxy.com`).

**After install**

| Command | Purpose |
|---|---|
| `agentboot` | Chinese console menu: install agents / models / mirrors / custom offline builds |
| `ab` | Built-in fallback agent — **free Agnes model, works immediately** |

> On Windows, newly installed commands need a **new terminal window** to appear in PATH.
>
> The online installer fetches and enforces a same-origin `.sha256` sidecar, then atomically switches the complete app directory. A corrupt download or failed upgrade does not overwrite the current version.

---

## 📦 One-command offline install (no internet needed)

Three steps: **① get an offline package → ② copy & extract → ③ run the offline installer**. No internet and no unzip software required on the target machine.

### Step 1 — Get an offline package

- **Option A**: download from [Releases](https://github.com/bit-cook/AgentBoot/releases)
  - `AgentBoot-offline-v1.1.0-win-x64.zip` (Windows x64)
  - `AgentBoot-offline-v1.1.0-linux-x64.tar.gz` (Linux x64)
  - `AgentBoot-offline-v1.1.0-darwin-arm64.tar.gz` (Apple Silicon)
  - `AgentBoot-offline-v1.1.0-<platform>-sfx.sh` (POSIX self-extracting single file)
- **Option B — build your own slim package** (recommended; see [Custom offline packages](#custom-offline-packages-slim)):
  pick platforms and agents, output goes to `dist/`.

### Step 2 — Extract (no unzip software needed)

| Target machine | How |
|---|---|
| Windows (any) | Right-click the ZIP → Extract All (built into Explorer) |
| Windows 10/11 (CLI) | `tar -xf AgentBoot-offline-v1.1.0-win-x64.zip` |
| Linux / macOS | `tar -xzf AgentBoot-offline-v1.1.0-<platform>.tar.gz -C ~` |
| Minimal POSIX | `sh AgentBoot-offline-v1.1.0-<platform>-sfx.sh` (self-extracting, uses only base64 + tar) |

### Step 3 — Run the offline installer

**Linux / macOS**

```bash
cd ~/AgentBoot
sh install-offline.sh                     # install + open console menu
sh install-offline.sh --all               # install every offline-capable agent
sh install-offline.sh claude-code qwen-code   # specific agents only
```

**Windows**

```powershell
cd AgentBoot
powershell -NoProfile -ExecutionPolicy Bypass -File install-offline.ps1          # install + menu
powershell -NoProfile -ExecutionPolicy Bypass -File install-offline.ps1 -All     # all agents
powershell -NoProfile -ExecutionPolicy Bypass -File install-offline.ps1 -Agents claude-code,qwen-code
```

### What the offline installer does

1. Verifies the `payloads/` bundle integrity;
2. Installs the AgentBoot app itself;
3. Python: system python3 on Linux/macOS; on Windows deploys a **portable Python** from the package (no admin);
4. Node: deploys the bundled Node 22 runtime when the system has none;
5. Copies the selected agents' payloads directly (no npm), generates command shims;
6. Registers `~/.local/bin` (Windows: `%LOCALAPPDATA%\AgentBoot\bin`) into the user PATH (idempotent);
7. `ab` works immediately: Agnes free model online; local models (Ollama / LM Studio) for fully-offline machines.

### Offline package layout

```
AgentBoot/
├── install-offline.sh / .ps1
├── MANIFEST.txt
├── core/ agents/ tools/ scripts/ ...
└── payloads/
    ├── python/win-embed.zip
    ├── node/<linux-x64|win-x64|darwin-arm64>/
    └── agents/<agent-id>/<platform>/node_modules/
```

### Offline troubleshooting

| Symptom | Fix |
|---|---|
| "payloads/ not found" | Run from the extracted package root, or pass `--payload <path>` |
| No python3 on Linux | `apt install python3` / `dnf install python3` / `apk add python3`, then re-run |
| Command not found after install | Reopen the terminal; or `export PATH="$HOME/.local/bin:$PATH"` |
| Missing payload for an agent | The selected pack does not contain it — rebuild on the target platform with menu [7] |
| `ab` can't reach the model | Expected fully offline — configure a local model in menu [4] |

---

## 🧩 Custom agents (beyond the registry)

**Menu wizard**: `agentboot` → `[2]` → `+` → pick method (npm / pip / install-script URL), name and command → save & optionally install. Appears in the list with a ★.

**Command line**

```bash
python core/menu.py add-agent myagent npm @scope/some-agent some-cmd
python core/menu.py add-agent myagent pip some-agent-pkg some-cmd
python core/menu.py add-agent myagent script "https://example.com/install.sh" some-cmd
python core/menu.py add-agent --list
python core/menu.py add-agent --del myagent
```

Stored in `~/.agentboot/custom-agents.json` — survives upgrades. Same install pipeline as built-ins (mirrors included).

> Hermes' offline payload contains a platform-specific Python venv and must be built on its target platform (for example, Windows on Windows and darwin-arm64 on Apple Silicon). The builder explicitly drops cross-target Hermes partial payloads instead of shipping a package that cannot run. Other npm Agents still support cross-target `--os/--cpu` packaging.

## 📦 Custom offline packages (slim)

The v1.1 Release provides verified Codex slim packs. Build a target-platform pack with only what you need:

**Menu**: `agentboot` → `[7] Build custom offline package` → pick platforms → pick agents → build.

**CLI**

```bash
python core/menu.py build-offline win-x64 claude-code,pi
python core/menu.py build-offline linux-x64,darwin-arm64 coco,pi,hermes
```

Custom packs use the same structure and install flow as Release packs. Size depends on the selected Agents and runtimes. The build machine needs internet; Hermes also requires Git and must be built natively on the target platform.

## 🌏 China network adaptive

- Auto-detects `registry.npmjs.org` reachability and enables mirror mode;
- npm → npmmirror, Node runtimes → npmmirror binary mirror, pip → Tsinghua mirror;
- Multi-source downloads: `boot.ide.pub` → GitHub Pages → GitHub Releases → `ghfast.top` / `gh-proxy.com`;
- Proxy: menu `[5]`, stored for npm and AgentBoot downloads;
- Force with `AGENTBOOT_MIRROR=cn|off`.

## 🧠 Model providers

`ab` → `/model`, or menu `[4]` — both open the **model provider manager**:

```
---- Model Providers ----
  [1] agnes     agnes-2.5-flash  (https://apihub.agnes-ai.com/v1) ← current
  [s] Switch   [a] Add provider   [d] Remove provider
  [f] Failover order   [t] Test current   [0] Done
```

- **Agnes free model** (built-in preset): zero config, first run works;
- **Custom providers**: any OpenAI-compatible endpoint, named, switchable, removable;
- **Local models (fully offline)**: Ollama (11434), LM Studio (1234), vLLM presets;
- **Failover order**: primary failure switches automatically (e.g. `agnes → ollama`);
- Config file: `~/.agentboot/config.json`.

**Which agents talk to Agnes out of the box?** Codex and Qwen Code are auto-wired (config.toml / OPENAI_* env) after install; OpenCode gets an `opencode.json`; Claude Code (Anthropic protocol) and Gemini CLI (Google protocol) need their own accounts.

## 🧰 Built-in agent (ab)

Single file, zero third-party dependencies (Python stdlib only), sub-second startup:

- Tools: run commands (dangerous ones blocked/confirmed), read/write/edit files, list dirs, `search_files`, fetch web pages;
- Offline Linux knowledge base (9 topics, 60+ sections) — usage lookups, operations, fixing common problems;
- Streaming output, session persistence (`ab -c`, `/继续`), context auto-trimming, `/bench` benchmark;

```bash
ab                                  # interactive
ab run "check disk usage"           # one-shot task
ab linux 查看端口占用                # query the knowledge base
ab doctor                           # environment check
ab bench                            # performance benchmark
```

## 🔧 Upgrade & uninstall

```bash
# upgrade: re-run the online one-liner (config preserved)
curl -fsSL https://boot.ide.pub/install.sh | sh

# uninstall one or more Agents (keeps config, credentials, and sessions)
agentboot uninstall codex
agentboot uninstall codex,qwen-code

# remove CoCo and its user data (irreversible)
agentboot uninstall coco --purge

# uninstall AgentBoot itself (also removes AgentBoot config)
rm -rf ~/.agentboot ~/.local/bin/agentboot ~/.local/bin/ab        # Linux/macOS
rmdir /s /q "%USERPROFILE%\.agentboot" & rmdir /s /q "%LOCALAPPDATA%\AgentBoot"   # Windows
```

You can also choose menu `[9] Uninstall Agents`. AgentBoot records ownership in `~/.agentboot/installed-agents.json`, so an unrelated command with the same name is never removed. Normal uninstall preserves every Agent's config and sessions; `--purge` currently has a defined data-removal boundary for CoCo only. Legacy installs are cleaned automatically only when ownership can be proven from an AgentBoot payload directory or marked shim; otherwise the command stops with manual removal guidance.

## ❓ Online install troubleshooting

| Symptom | Fix |
|---|---|
| `curl` missing | `wget -qO- https://boot.ide.pub/install.sh \| sh`, or install curl |
| All sources fail | Use the offline package, or set a proxy first |
| Windows "scripts disabled" | Use the `-ExecutionPolicy Bypass` command from the docs |
| python3 auto-install failed | Install Python manually, then re-run |
| `agentboot` not found | Reopen terminal / `source ~/.bashrc`; on Windows open a new terminal |

## ❓ FAQ

**Which agents work with the free Agnes model right after install?**
Codex and Qwen Code are auto-wired; OpenCode gets an `opencode.json`; the built-in `ab` always defaults to Agnes. Claude Code (Anthropic protocol) and Gemini CLI (Google protocol) need their own accounts.

**Why is codex pinned to 0.90.0?**
0.100+ removed the chat wire protocol and 0.15x sends private tool types that OpenAI-compatible gateways reject. The pin keeps Agnes working out of the box; upgrade and use official login if you prefer.

**Release pack or custom pack?**
Slim when the target machine needs 1–2 agents (e.g. 89MB win-x64 + Pi); full when unsure. Missing agents in a slim package are reported clearly during install.

**How do I verify performance?**
`ab bench` — KB query latency (cold/warm), model first-token latency with and without TLS handshake.
