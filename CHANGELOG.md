# 更新日志

## v1.1.0 (2026-08-30)

- 新增 Agent 安全卸载：菜单 `[9]`、`agentboot uninstall <id>`、批量卸载与 CoCo `--purge`。
- 新增原子安装归属清单，区分 AgentBoot 管理安装与系统同名命令；兼容可证明归属的 v1 遗留安装。
- 在线、离线、CoCo 与自定义 Agent 安装成功后统一记录来源、包名、命令与安装前缀。
- 新增固定卸载验收、安装追踪集成测试、Python 编译门禁和确定性在线包构建。
- Pages 工作流在核心代码变化时自动测试并重建在线 tar/zip，避免源码与实际下载包脱节。
- `ab` 命令链按每个子命令判定风险，`safe` 真正只读，非交互 `smart` 不再静默放行写操作。
- Node 便携运行时升级到 22.23.2，按 Agent 精确校验最低版本；修复 Windows/ARM/macOS 离线平台映射。
- 在线包新增 SHA-256 旁车校验和原子升级回滚；构建器以临时文件原子发布且结果可复现。
- 自定义脚本仅允许 HTTPS，下载到临时文件后以固定参数执行，消除 URL shell 注入；脚本上限 4 MiB。
- 修正 `ab bench` 首字延迟计时、全部 60 个 Linux 知识库段落索引、`ab` 子命令包装器和 CoCo 数据备份恢复。

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
- 模型提供商管理器：Agnes 零配置开箱即用；自定义提供商命名管理（增删切换）、本地模型预设、故障切换顺序；ab 与菜单共用。
- 文档与站点升级：产品级主页（特性卡片 / Agent 全表 / 复制按钮 / 深色模式）、README 重构、安装指南目录与 FAQ。
- 内置 Agent 深度优化：TLS 连接复用（每轮对话实测省约 440ms 首字延迟）、知识库预建索引（热查询亚毫秒）、上下文预算自动瘦身、会话持久化（`ab -c` / `/继续`）、新增跨平台 `search_files` 工具、模型源故障自动切换（`fallback`）、`/bench` 性能基准。
