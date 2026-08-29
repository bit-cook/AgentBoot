# 更新日志

## v1.0.0 (2026-08-29)

首发版本。

- 内置最小 Agent（ab）：单文件、零第三方依赖、流式输出，默认 Agnes 免费模型，
  支持自定义 OpenAI 兼容接口与本地模型（Ollama / LM Studio）。
- 内置离线 Linux 知识库：可查阅用法、操作系统、修复常见问题。
- 中文控制台菜单（agentboot）：环境体检 / 在线安装 Agent / 离线安装 / 模型配置 / 镜像代理。
- Agent 目录：Claude Code、Codex、Qwen Code、OpenCode、CodeBuddy、MiMo Code、Cline、
  Gemini CLI、iFlow CLI、Aider。
- 中国网络自适应：自动探测并切换 npmmirror、Node 运行时镜像、pip 清华源、代理支持。
- 一键在线安装（Linux/macOS/Windows）与一键离线安装（含自解压包）。
- Cloudflare Worker 分发：`curl -fsSL https://boot.ide.pub/install.sh | sh`。
- GitHub Pages 分发入口：`curl -fsSL https://bit-cook.github.io/AgentBoot/install.sh | sh`。
- 新增 Agent：Hermes Agent（自我进化智能体，需 Git）、OpenClaw（多渠道个人 AI 网关）、Pi Coding Agent（pi.dev 同源 npm 包）。
