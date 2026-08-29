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
- 新增 Agent：Hermes Agent（自我进化智能体，需 Git）、OpenClaw（多渠道个人 AI 网关）、Pi Coding Agent（pi.dev 同源 npm 包）、CoCo Agent（脚本安装，Linux/macOS）。
- 新增自定义 Agent：菜单向导或 `add-agent` 命令可添加注册表之外的任意 Agent（存于用户目录，升级不丢）。
- 注册表支持 `os` 平台限制与 `requires` 前置依赖检查；脚本类安装自动加镜像兜底。
- v1.0.0 调整：CoCo Agent 置顶（vendor 更名 BitCook）；除 Aider（pip 生态）外全部 Agent 支持离线安装，离线载荷补齐 Hermes（含完整 Python 运行时）/ OpenClaw / Pi / Gemini CLI / iFlow CLI。
- 新增自定义离线包构建：菜单 [7] 向导或 `build-offline` 命令，自选平台与 Agent 生成瘦身离线包（如 win-x64 仅 Pi ≈ 89MB）。
- 内置 Agent 深度优化：TLS 连接复用（每轮对话实测省约 440ms 首字延迟）、知识库预建索引（热查询亚毫秒）、上下文预算自动瘦身、会话持久化（`ab -c` / `/继续`）、新增跨平台 `search_files` 工具、模型源故障自动切换（`fallback`）、`/bench` 性能基准。
