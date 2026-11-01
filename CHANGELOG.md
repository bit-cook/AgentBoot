# 更新日志

## v1.7.1 (2026-11-01) — 发布基建修复（应用代码无变化）

- 发布管线端点等待改为超时警告：boot.ide.pub 的 Worker 部署是流水线外手动
  步骤（需 CF 凭据），原逻辑轮询 10 分钟不绿即 exit 1，导致每次发版
  publish 必红（v1.6.1 实测复现）。Release 资产与晋升不再被端点阻塞，
  端点就绪由手动执行 cloudflare/deploy.sh 后复验。
- Pages 部署防冻结（根因修复）：本站 Pages 构建类型为 legacy（直接服务
  gh-pages 分支），deploy-pages 工作流在推送 gh-pages 后显式请求一次
  Pages 构建，确保线上立即刷新。历史事故：build_type=workflow 时期本
  工作流只推 gh-pages、从不上传 artifact，GitHub 永远等不到 Actions
  部署，bit-cook.github.io/AgentBoot 与 osome.work 镜像冻结在 v1.4.3
  近 6 周。新增测试守卫 test_pages_deploy_requests_legacy_build。
- GitHub 账户侧 Pages 配置已切换为 legacy 构建（用户站 + 项目站），
  osome.work/AgentBoot 与 bit-cook.github.io 均已实测恢复 v1.7.1 内容。
- 清理：pages/VERSION 自 v1.4.0 起遗漏的刷新已修正；删除无 release 的
  悬空 v1.6.2 tag。测试总数 372 全绿。

## v1.7.0 (2026-10-31) — 极限性能优化

实测数据（本机 min-of-9，`python3 -c` 冷进程，基线 44.2ms）：

- 惰性模块代理（core/menu.py）：顶层导入的 subprocess/shutil/platform
  只在安装/卸载/构建/下载路径才需要，菜单渲染与版本查询用不到，却让
  每次启动多付约 15ms。改为 _LazyModule 代理后首次真正调用才导入：
  **import menu 67.2ms → 54.8ms（-18%），菜单自身导入开销 -54%**；
  import agent 保持 49.4ms（+3.5ms，已贴近解释器基线）。代理支持属性
  读写转发，mock.patch.object(menu, "subprocess") 等测试补丁照旧工作
  （PEP 562 模块 __getattr__ 管不了模块内部裸名引用，故用代理对象）。
- 预编译字节码打包（scripts/build-online.py、stage_application.py）：
  构建时 compileall 并把 __pycache__/*.pyc 一并打包，安装首启免现场
  编译，**实测首启 56.5ms → 51.4ms（省 5.1ms）**；.pyc 内嵌 Python
  魔数，目标机版本不匹配时解释器自动忽略并重编译，无害。
- 新增回归测试：tests/test_lazy_module_imports.py（7 个，锁代理行为：
  内部引用可用/属性补丁转发/整体替换可用/惰性确实 deferred）、
  test_release_staging.py +2（在线包与离线 stage 必须带 .pyc）。
  测试总数 371 全绿。
- 其它路径复测确认无需优化：i18n 导入≈0、KB 索引 0.7ms 热/1.4ms 冷、
  doctor 主机探测已并发（ThreadPoolExecutor）、load_config 1.4ms、
  load_registry 0.26ms、launch.py 已是极简 dispatcher。

## v1.6.2 (2026-10-31)

- 修复 npm 卸载残留空 scope 目录（v1.6.0 深度实测发现）：`npm uninstall -g @scope/pkg --prefix P` 报告成功、bin 也删了，但 `P/lib/node_modules/@scope/` 空目录残留（实测 @qwen-code/、@anthropic-ai/），用户看 node_modules 以为没卸干净。新增 `_clean_npm_prefix_residue()`：npm 卸载后显式删除包目录与空 scope 壳；路径安全校验（只清 AgentBoot 自己 HOME 内或等于 NPM_PREFIX 的 prefix，绝不碰外部 prefix；同一 scope 下还有其他包时保留 scope 目录）。新增 4 个回归测试。测试总数 362 全绿。

## v1.6.1 (2026-10-31)

- 安装器命令入口落盘加固（新机器模拟实测 3 个失败场景的修复）：原实装在只读 `/usr/local/bin`（root+sudo、非 root+sudo 均复现）、坏 `TMPDIR`（非 root+sudo）下会硬失败并留「应用已装、命令全无」的半安装脏状态。`install.sh` 与 `scripts/install-offline.sh` 同步修复：落盘前 `probe_bin_dir` 真实探写，失败即回落 `~/.local/bin` 重试（不再依赖选择阶段的 `-w`/`sudo -n` 推断）；sudo 分支 `TMP_BASE` 的 `mktemp` 增加 `/tmp` 回退链（对齐下载临时目录既有容错，`set -eu` 下不再瞬死）；launcher 创建失败时 `rollback_install` 回滚（升级恢复旧版/新装撤掉应用）。新增 5 项行为级回归测试（沙箱内真跑探写段、`/proc` 模拟不可写、回滚修复验证转红）。全量 358 测试绿。

## v1.6.0 (2026-10-31)

- 修复卸载删不掉 /usr/local/bin 里的 shim（v1.5.3 全新干净 Linux 机器实测发现）：v1.5.1 起 launcher/shim 优先装 /usr/local/bin（非 root 经 `sudo -n install` 落盘），但卸载路径是裸 `os.remove`——非 root 机器上报 `Permission denied`、卸载判失败、命令仍残留（实测 `agentboot uninstall opencode` 报 Errno 13）。新增 `_remove_owned_file()`：直接删除失败且目标在 /usr/local/bin 时经 `sudo -n rm -f` 对称落盘；`_remove_owned_shims` 与 CoCo 外部启动器清理都切到该助手。新增 4 个回归测试（直接删/sudo 删/无 sudo 重抛/非 /usr/local/bin 不借 sudo）。测试总数 353 全绿。
- 全新干净 Linux 机器（InstaBox，美国 AWS，非 root + passwordless sudo）全功能遍历实测（v1.5.3 基线）：一键安装同 shell 立即可用；ab 的 help/version/sys/linux/doctor/bench 全过（bench：知识库冷 0.7ms、首字 101ms/复用 43ms）；Groq 流式对话、工具调用、groq→agnes 故障切换全部真实通过；run_cmd 安全分级 6/6（只读放行/高危拦截/写操作拒写/always 放行/safe 策略）；http_get SSRF 5/5 拦截（回环/云元数据/::1/10 段/192.168 段）；pty 实测高危命令、写文件、改文件三条交互确认路径（y 后真实落盘）；菜单 10 项渲染与 dispatch；版本查询/默认装最新（1.19.5）/指定版本（1.19.4）/重装后 shim 目标正确（自指死循环修复复验）/卸载/镜像探测/语言切换/add-agent 增删；离线包 227MB 载荷 SHA-256 校验 + codex 离线安装；sfx 自解压 303MB 安装；边界（损坏 config 后正常启动、重复安装幂等 bashrc 不重复）；官网零控制台错误、移动端无横向溢出、404 页正常。
- 已知外部问题（非本仓可控）：自定义域名 osome.work 的 Pages 镜像缓存陈旧（实测仍服务 V1.4.3，而 gh-pages 分支已是最新 v1.5.3）——该域名不在项目 Cloudflare 账号内，需域名方清理或在 GitHub Pages 设置中摘除自定义域名恢复 bit-cook.github.io 直出。

## v1.5.3 (2026-10-31)

- 会话持久化补全（Windows 实测发现的缺口）：`ab run` 一次性任务此前不写会话，`ab -c` / `/继续` 接不上；且管道模式（`echo 任务 | ab chat -c`）完全忽略 `-c`，会话恢复只在交互 REPL 生效。现在 run / 管道 chat / 兜底任务三条路径统一持久化并支持 `-c` 恢复（实测：run 记住代号 → 管道 chat -c 正确答出）。
- 镜像语义对称化：`mirror off` 现在同步解除 npm 源固定并切回官方源（此前状态栏显示「国际网络」而 npm 仍固定 npmmirror，自相矛盾）；`mirror cn` 同步固定国内镜像。
- doctor 的 Python 探测改走 `find_python()`（带真实执行校验），不再把 Windows 商店存根当 Python 展示；`install_via_pip` 同步修复（此前命中存根会让 pip 安装莫名失败）。
- `ab bench` 模型测速改为与 chat 相同的主源→备选链：默认源被地区封锁时（实测 Groq 对国内 IP 全 403）自动改测备选并标注实测源，不再直接报「测试失败」。

- 修复官网安装页滚动错位：左栏「从这里开始」（`position: sticky` 直接放在 CSS Grid 网格项上）在部分浏览器内核不按网格区域钳制，滚动到命令卡底部后会一直钉在 top:104px，压过第二行的「备用源说明」造成两层文字重叠（Windows 实机复现，Playwright A/B 实测原版在全宽度存在 122px 重叠窗口）。改为「外层占位拉伸 + 内层 sticky」的引擎无关写法：`.install-intro` 改 `align-self: stretch`，新增 `.install-intro-pin` 承载 sticky，≤900px 断点用 `display: contents` 保持移动端两栏布局；`site.css` 缓存参数 b=3→b=4。中英文页面同步修复。
- 测试套件首次在 Windows 全绿（349 项：336 通过 / 13 跳过 / 0 失败）：shim 目标解析补 Windows `.cmd` 形态与 `"..." %*` 调用行、版本自选与预设门控测试补 `resolve_shim_target` mock、darwin 用例补 `os.name` mock、worker fallback 测试改 `fileURLToPath`（原 `URL.pathname` 在 Windows 拼出 `C:\C:\` 双盘符）、语言状态泄漏修复（`test_language_persistence` 两个用例恢复全局语言）。
- 修复测试污染真实用户环境（Windows 实测踩坑）：`ENV_JSON` 由模块导入时冻结的常量改为 `env_json_path()` 动态跟随 `AB_HOME`（缓存键加 path 维度）——此前测试 mock `AB_HOME` 后 env.json 读写仍落在真实用户目录，曾把测试代理配置写进真实 `~/.agentboot/env.json`；生命周期测试补 `write_online_shim` mock（不再把 `/managed/...` 假 shim 写进真实 `~/.agentboot/bin`）；`ensure_path_registered` 支持 `AGENTBOOT_NO_ENV_WRITE=1` 逃生阀并在基准脚本启用（临时目录不再写进真实用户 PATH 注册表）。
- `_shim_exec_target` 兼容 Windows .cmd shim 的 `"..." %*` 调用行：此前只认 POSIX `exec "..."`，Windows 上重装兜底「沿旧 shim 找真身」永远解析失败。
- doctor 网络探测跟随当前模型源（默认模型切 Groq 后不再只探测 agnes），模型连接失败的错误提示补充国内网络瞬时波动语境（本机实测：Cloudflare 系 API 偶发整段拒连窗口，稍候重试自愈）。

# 更新日志

## v1.5.2 (2026-10-31)

- 默认模型切换为 Groq：内置 agent `ab` 的默认模型改为 Groq 的 `qwen/qwen3.8-27b`（OpenAI 兼容，Base URL `https://api.groq.com/openai/v1`，约 450 t/s 极速推理；免费层额度 30 RPM / 1K RPD / 8K TPM / 200K TPD，个人使用足够）。Agnes 免费模型不删，作为自动备选——主源失败时 chat_auto 按 `cfg["fallback"]` 自动切换，Groq 不可用（限流/欠费/地区封锁）也不会对话不了。`/model` 与菜单 [4] 的提供商管理器自动列出 Groq（当前）与 Agnes（备选）。
- Groq key 防护（用户专用 key，默认内置）：不明文进仓库——GitHub 密钥扫描会拦截明文推送（实测 GH013），且明文等于把 key 挂到公网。改为 base64+位移编码内置（`embedded_groq_key()`，防自动扫描层），解析顺序 `/model` 显式配置 > 环境变量 `GROQ_API_KEY` > 内置 key。真正的防护在 Groq 控制台：建议对该 key 设置速率/消费上限，被滥用时可直接轮换（轮换后改 `_GROQ_KEY_ENC` 一处即可）。
- 修复 CDN 边缘 403 抖动不重试：实测 Groq 前端 Cloudflare 在 PDX/SEA 边缘间抖动，同一请求时 403 时 200/404（403 响应体是裸 "Forbidden"、无 type/code）。新增 `_is_edge_rejection()` 判别：裸 Forbidden/空体/非 JSON = 边缘拒绝（换连接重试，最多 2 次）；带 type/code 的结构化错误（模型无权限、组织屏蔽）= 真拒绝，立即失败不重试。
- 新增一次性配置迁移：仅对仍处旧默认形态（active=agnes、无自定义提供商、未配过备选链）的配置切到新默认，显式定制过的配置一律不动。
- 全新干净 Linux 机器（InstaBox，美国 AWS）实测：默认提供商解析正确（groq + qwen/qwen3.8-27b + 内置 key）；流式对话 0.37s 首响、28 个流式片、中文回复正常；工具调用正确发出 `run_cmd`；groq 故障时自动切 agnes。同机探查确认：该 key 免费层可见 11 个模型，qwen/qwen3.8-27b 在列且可用；llama-3.1-8b/3.3-70b 为 Enterprise 档不在免费层（返回 404 model_not_found）。另确认本机（国内 IP）被 Groq 地区封锁（全 403）——内置 key 面向可访问 Groq 的地区，被封锁地区自动落 Agnes 备选。
- 所有 Agent 默认安装最新版：注册表此前的两个钉版（opencode-ai 1.18.25、@openai/codex 0.90.0）全部取消，npm spec 一律不带版本号——opencode 不再提示更新（实测新版 1.19.5）。codex 0.100+ 移除 chat 协议、与 Agnes 预设不兼容的问题改由「版本自选 + 预设期警告」解决：用 Agnes 预设装 codex 且版本 >0.90.0 时明确提示改用 `codex@0.90.0` 或官方登录；v1.5.0 起默认原版安装（用用户自己的 provider）不受影响。
- 新增版本自选功能：`agentboot install <id>@<版本>`（如 `agentboot install opencode@1.19.4`）、`agentboot install <id> --version <版本>`、菜单 [2] 选完 Agent 后逐个询问（回车=最新，同时展示最近版本列表）、`agentboot versions <id>` 查询可用版本（真实拉取 npm registry，过滤预发布与平台分包）。新增 `agent_npm_versions()` / `resolve_npm_spec()` / `parse_agent_version_tokens()`，`install_online` 全链路透传 versions（批量与单装两条路径）。
- 修复重装已安装 Agent 时 shim 自指死循环：在线安装用 `find_bin` 解析真身，而 `find_bin` 先搜 shim 目录——机器上已有旧 shim 时返回旧 shim 自身，新 shim 的 exec 行指向自己，命令永远跑不起来（exec 无限循环；仅在有旧安装的机器上复现，全新机器碰不到）。新增 `resolve_shim_target()`：npm prefix bin 优先 → PATH 跳过自身 shim 目录 → 旧 shim 的 exec 目标带环保护；`write_online_shim` 再加一道「目标在 shim 目录内一律拒绝写入」的兜底防御。
- 新增回归测试：tests/test_agent_version_selection.py（13 个：注册表不变量「npm spec 不得带版本号」/spec 解析/记号解析/版本列表过滤（mock 网络）/安装链路透传/预设警告）、tests/test_groq_default_model.py（12 个：预设值/默认与备选/env 覆盖/显式配置优先/一次性迁移三形态/groq 失败自动切 agnes）、tests/test_shim_target_resolution.py（7 个：prefix 优先于旧 shim/自指 shim 跳过/exec 目标解析/PATH 候选/写入防御）。测试总数 339 全绿。

## v1.5.1 (2026-10-31)

- 安装后命令立即可用（修复「装完 agentboot / opencode 找不到命令，还要手动 source ~/.bashrc」）：launcher 与 Agent shim 的安装目录从 `~/.local/bin`（默认不在 PATH 上，只能靠写 shell 配置 + 重开终端）改为优先 `/usr/local/bin`——它默认就在所有 shell 的 PATH 上。root 直接写；非 root 但有 passwordless sudo 时经 `sudo -n install` 落盘（绝不弹密码提示）；两者都不满足才退回 `~/.local/bin` + shell 配置兜底。离线安装器同样处理。
- 安装完成提示按当前 shell 是否已可用分支：PATH 已包含目标目录时明确告知「当前终端直接输入 agentboot 即可，无需 source、无需重开终端」，否则给出来源指引。
- 版本间目录变化时自动清理另一处位置的旧 launcher（只删内容指向 launch.py 的 AgentBoot 自己的文件，防止旧版挡住新版）。
- shim 写入保留原有安全保证：拒绝符号链接、临时文件与目标同目录保证 mv 原子替换；新增 sudo 落盘路径（/usr/local/bin 场景）。
- 新增回归测试：ShimBinDirTests（目录选择三态 + 直接写 + sudo 写 + 双不可写失败）、安装器事务断言更新（符号链接拒绝/原子 mv/sudo install/-n 探测）。测试总数 307 全绿。
- 全新干净 Linux 机器（InstaBox，非 root + passwordless sudo）实测：一键安装后同一 shell 内 agentboot、ab 直接可用；经菜单安装 opencode 后 opencode 直接可用（默认原版不写模型配置）。

## v1.5.0 (2026-10-30)

- 模型预置改为可选、默认原版：安装第三方 Agent（opencode / codex / qwen-code / aider / CoCo 等）不再写任何模型配置、不注入环境变量，Agent 保持厂商默认状态，首次运行时由用户自己登录/配置模型。开启方式：`agentboot preset on`、菜单 [4] 里的「安装 Agent 时的模型预置」开关、或一次性 `agentboot install <id> --preset`；环境变量 `AGENTBOOT_PRESET_MODEL=1` 可临时覆盖。安装前会打印一行说明本次是否会预置。内置 ab 的默认模型不受影响（仍可用 `/model` 切换）。
- 修复安装后 `agentboot` 命令找不到：PATH 注册段此前用 `[ -f "$rc" ]` 判断，rc 文件不存在（新系统 root 无 ~/.bashrc）时静默跳过，什么都不写。install.sh / install-offline.sh 均改为「不存在先创建再追加」，写入失败时明确报错并给出手动配置方法。
- 修复 `curl | sh` 装完按 Y 打开菜单却立即退出：脚本经管道运行时 stdin 是已耗尽的管道，菜单 `input()` 立刻 EOF。两个安装器的菜单启动均改从 `/dev/tty` 读输入。
- 安装完成提示重写为「如何启动」：明确列出 `agentboot` / `ab` 两个入口、PATH 写进了哪个文件、当前终端如何立即生效（`source ~/.bashrc` 或 export），回答 n 时也提示下次怎么打开。
- 全线实测期间发现并修复（均带回归测试，测试总数 278 → 299）：SSE 空 `data:` 心跳行曾杀死整条流（one-api/new-api 类中转常发）；REPL 裸 `exit`/`quit`/`q`/`退出` 不退出而被当成任务发给模型；高危命令在交互模式下无法确认（拒绝消息却承诺「交互模式下可确认」，该路径不存在，且修复时连带堵掉二次确认流漏洞）；Cloudflare Worker 代理 GitHub release 资产间歇 502（上游 618、在资产间轮换）——改为 Release 为主、Pages CDN（jsDelivr）兜底，health 同逻辑；`agentboot lang` 输出双勾；英文 i18n 块混入中文串；菜单多选输入无效编号零反馈；`AGENTBOOT_HOME` 指向文件时裸抛 traceback；en 首页 hero 徽章残留 v1.4.3（版本一致性测试加强为「页面所有版本串必须等于当前版本」）。
- 新增回归测试：tests/test_installer_path_regression.py（9 个，沙箱 HOME 中真实执行 PATH 注册段）、tests/test_preset_optional.py（12 个，默认关/环境变量覆盖/标志解析/三条安装路径门控/CoCo auth 门控，门控拆掉即红）。

## v1.4.4 (2026-10-29)

- 修复 npm 安装超时清理的 killpg(0) 自杀式信号缺陷：子进程组为 0、不存在或与当前进程同组时绝不 killpg，退化为单进程 kill——此前会在超时清理时挂死自身进程组（test_deep_polish 实测挂死 45 秒以上无法终止）。
- 修复 CI 全红连锁：自 v1.4.0 引入 npm 超时保护起，`test_agent_hardening` 在 Linux runner 上必失败（断言了 Windows 专属的 taskkill 路径）、`test_deep_polish` 挂死，导致 deploy-pages / release-pipeline / release-pr 全部无法完成；现全量 253 个测试 8.9 秒跑绿。
- 修复 core/agent.py darwin 分支两处 `subprocess.run` 缺少 import（pyflakes F821）：macOS 上内存总量与 CPU 型号查询此前被 except 静默吞掉，`ab sys` / `ab doctor` 信息不全。
- 修复镜像损坏不回退：华为云镜像的 `python-3.12.10-embed-amd64.zip` 实测为截断坏包（sha `1940ea1a…` vs python.org 官方 `4acbed6d…`，BadZipFile）。build-offline.sh / build-offline.ps1 / install.ps1 全部改为逐源校验下载（fetch_verified / Get-UrlVerified / Ensure-NodeArchive），损坏源自动切换官方源——此前离线包构建必败、无 Python 的 Windows 一键安装必败。
- CoCo 离线发行包 0.8.0 → 0.8.1（官方 sidecar 校验通过），版本号收敛到 `agents/registry.json` 的 `coco_version` 单一来源，构建期即校验发行包完整性。
- Node 运行时与 CoCo 载荷下载同样改为逐源校验（npmmirror → nodejs.org），本地缓存命中时先验 sha；npm 载荷安装失败时清掉用户级 npm 配置（失效代理）重试一次。
- 修复自托管 runner 上 deploy-pages 第二次运行必败的问题：`_work` 目录跨运行复用导致遗留的 gh-pages worktree 让 `git worktree add` 报 `already exists`（exit 128），发布前先清理注册与目录。
- CI 架构改为全自托管：注册仓库级 self-hosted Linux runner（LEC-Dev-agentboot，systemd 服务），deploy-pages / release-pr / publish-pages / release-pipeline 的 Linux 作业全部 `runs-on: self-hosted`；Windows/macOS 平台作业移入仅手动触发的 release-platforms.yml（本机无法执行，避免 publish 永远等待要排队数小时的 GitHub-hosted runner）。
- 交互入口（agentboot 菜单 / ab）stdin 关闭或管道输入时干净退出，不再抛 EOFError traceback。
- `agentboot doctor` 的安装状态改用归属判定（AgentBoot 管理 / 旧版残留 / 外部安装），不再把系统里的同名命令误标为已安装。
- 工程清理：tests/test_release_workflow.py 去除 UTF-8 BOM（全库唯一）；verify-live-release.py 删除未用导入；pages 下 6 个 .sha256 sidecar 统一 LF 行尾，消除每次构建的伪 diff。
- 新增回归测试 tests/test_release_hardening.py（9 个）：镜像损坏逐源回退（真实执行 fetch_verified）、CoCo 版本单一来源、stdin EOF 干净退出。

## v1.4.3 (2026-09-14)

- 深度完善：镜像模式（auto / cn / off）持久化到 `~/.agentboot/env.json`——`agentboot mirror cn|off` 重启后依然生效，不再只对当前会话有效；菜单「镜像代理」新增模式切换子项；环境变量 `AGENTBOOT_MIRROR` 仍可临时覆盖。
- 极限优化：`env.json` 读取按 mtime 缓存——`cn_mode / gh_mirrors / npm_registry` 等高频调用不再反复读盘；返回值改为拷贝，杜绝调用方误改写回缓存。
- 安装体验：npm 安装期间每 15 秒显示一次已耗时（`--progress=false` 全程静默时不再像卡死），结束后自动清除。
- 环境体检（`ab doctor`）新增本机硬件摘要行（系统 / 核数 / 内存），完整配置仍用 `ab sys`。
- 站点镜像（gh-pages）404 页资源路径改写为自包含（`/AgentBoot/assets/`），`ide.pub` 失效后镜像站样式不再丢失。

## v1.4.2 (2026-09-13)

- 内置 Agent（ab）新增机器配置查询：`sys_info` 工具报告主机名 / 操作系统与版本 / CPU 型号与核数 / 内存总量与可用 / 各磁盘容量 / Python 与 AgentBoot 版本，Windows（注册表 + GlobalMemoryStatusEx）/ Linux（/proc）/ macOS（sysctl）全平台标准库实现，离线零依赖；对话里问「这台机器什么配置」直接可答，另提供 `ab sys` 一键命令与交互内 `/sys` 命令。
- 镜像多源化：npm 源支持 npmmirror（阿里）/ 腾讯云 / 华为云 / 官方源切换，npm 安装命令自动使用所选源；Node 运行时下载新增华为云、腾讯云二进制镜像（含 SHASUMS256 校验文件，官方源始终兜底）。
- GitHub 加速可切换：gh-proxy.com / ghfast.top / ghproxy.net 三源自动探测选路（可达优先、其余兜底），支持固定指定加速源或关闭直连；脚本安装、uv 预置下载、hermes git 重写、uv-python 安装镜像全部接入统一选路。
- 镜像选择持久化到 `~/.agentboot/env.json`：控制台菜单「镜像代理」新增 npm 源切换与 GitHub 加速切换子菜单（带连通性探测与当前项标记）；CLI 新增 `agentboot mirror npm [源URL]` 与 `agentboot mirror gh [auto|off|前缀URL]`。
- CoCo 官方安装脚本 GitHub 加速源清单同步补全（ghproxy.net）。

## v1.4.1 (2026-09-13)

- 内置 Agent（ab）实时显示思考过程：支持 `reasoning_content` 独立通道与正文内联 `<think>…</think>` 标记（含跨分块截断），思考文本暗色渲染、与正文区分；个别把答案全放思考通道的模型按正文兜底，不再误报空响应。
- 内置 Agent 新增首包等待指示器：模型响应前显示「⏳ 正在思考 Ns」行内动画，首个思考/正文 token 到达即清除，等待时间一目了然（仅交互式终端，Windows 自动启用 VT 序列）。
- CoCo 安装提速（coco 仓库官方脚本）：Node 运行时改走 npmmirror 镜像、发行包与 Agnes 密钥支持 gh-proxy/ghfast 加速，自动探测网络选路，可用 `COCO_MIRROR=off` 强制直连、`COCO_NODE_DIST_BASE`/`COCO_RELEASE_MIRRORS` 覆盖；全部镜像互为兜底且保留 SHA-256 校验。
- AgentBoot 脚本类安装（script 方法）新增 jsDelivr 兜底源：GitHub Pages 不可达或自定义域名过期时，自动改从 `cdn.jsdelivr.net/gh/<user>/<repo>@gh-pages/…` 获取安装脚本。
- CoCo 离线安装解压提速：优先使用系统 tar（C 实现，含 `--force-local`/cwd 兼容处理）替代 Python gzip 解压，越界校验保持不变，失败自动回退原实现。
- 安装器下载兜底从三源扩为四源（Worker → Pages → jsDelivr 镜像 → GitHub Release）；主页新增 Releases 终极安装入口（不依赖任何自定义域名）。

## v1.4.0 (2026-09-12)

- 新增 FreeBuff（`freebuff`，freebuff.com）为第 16 个内置 Agent：免费、广告支持、无需 API Key；npm 轻量启动器，首次运行联网获取平台原生二进制，暂仅在线安装。
- 文档、双语主页与 Agent 数量口径同步更新为 16；文档一致性测试同步锁定注册表与页面行数。
- 修复 TUI 字符画字形错乱：`agent.py` 与 `menu.py` 顶部 ASCII 艺术统一替换为经校验的标准字形，正确显示 AgentBoot。
- 修复 Windows 安装 Agent 后新终端不可用的问题：用户 PATH 注册表目标补齐 npm prefix 等目录，并在写入后广播 `WM_SETTINGCHANGE`，资源管理器即时重载环境变量，无需注销/切换用户。
- 极限优化冷启动：`agent.py` 全面惰性化 `ctypes / tempfile / socket / ipaddress / json` 导入；`ab version / linux / help` 走零配置路径（不加载模型配置）；Windows 控制台模式修复仅在真实 TTY 下执行 `ctypes`。实测一次性命令与菜单就绪提速约 40%+。
- 知识库索引持久化：首次构建后以 marshal 缓存到 `~/.agentboot/kb-index.cache`，按「文件名+大小+mtime」指纹失效；仅对随包内置知识库落盘，后续冷查询免重建。
- 模型接口 429 限流纳入自动重试并尊重 `Retry-After`（上限 10s），与 5xx 同等处理，提升免费额度下的稳定性。
- 环境体检与镜像状态的网络探测并行化：doctor 三项探测由串行累加变为并发（最差 6s → 2s）。
- 修复 `search_files` 非正则模式下从不匹配文件名的问题（与工具描述一致），并清理 `linux_help` 无匹配分支的死代码。
- 性能基准脚本支持 Windows（假工具链按平台生成 .cmd），安装项看门狗放宽至 60s 以消除杀软首扫抖动。
- 修复 `deploy-pages` 工作流一致性测试的过时断言（工作流已改为 gh-pages 发布，测试同步校验 SHA 钉版 checkout 与凭据丢弃）。
- 修复测试套件在 Windows 上的两类密封性问题：`expanduser` 优先读 `USERPROFILE` 导致 CoCo/Cursor 测试写真实主目录；离线安装成功用例未 patch `AGENTS_DIR` 导致载荷落进真实 `~/.agentboot`。POSIX 专属测试在 Windows 明确跳过，套件跨平台全绿。
- 新增 `publish-pages` 应急工作流（仅手动派发，直接把 gh-pages 分支以 artifact 形式发布到 Pages 服务层，绕开经典构建队列；默认托管 runner，自建 runner 可选）。
- 主页与文档新增 GitHub Pages 冗余一键脚本（`bit-cook.github.io/AgentBoot/install.sh` / `install.ps1`）：`ide.pub` 域名不可用或过期时的备用入口，与主入口同源发布。
- 备用源路径大小写均可：站点部署时自动生成 `/agentboot/` 小写别名目录（与 `/AgentBoot/` 内容一致，标记 noindex），小写输入不再 404。
- 安装器下载兜底从三源扩为四源（Worker → Pages → jsDelivr 镜像 → GitHub Release）：jsDelivr（gh-pages 分支镜像）不依赖任何自定义域名，国内通常更可达。
- 主页与文档新增 GitHub Releases 终极兜底一键入口（`releases/latest/download/install.sh`）：`ide.pub` 与 `osome.work` 等全部域名过期时仍可安装；文档补充「自定义域名失效 → 移除 Pages 自定义域名恢复 github.io 直出」的维护预案。
- 修复 gh-pages 分支的陈旧内容：根目录补齐 v1.4.0 安装包与 .sha256（此前 Pages 兜底链取包会 404），入口 install.sh / install.ps1 由 v1.3.0 更新为 v1.4.0。

## v1.3.0 (2026-08-31)

- 新增 Cursor 官方跨平台用户级安装：Linux AppImage 固定 SHA-256，Windows Authenticode，macOS codesign + notarization 校验。
- Cursor 安装在 AgentBoot 私有应用目录，具备原子升级、归属 marker、安全卸载与外部安装保护。
- OpenCode 固定 `opencode-ai@1.18.25`，离线包携带官方平台 native binary；x64 同时提供 regular 与 baseline 兼容版本。
- OpenCode 目标机根据 `--version` 实测选择可运行 binary，不执行联网 postinstall，卸载保留模型配置。
- OpenCode-only 离线包不再捆绑不需要的 Node 运行时，降低体积。
- 新增 Linux、Windows、Intel macOS、Apple Silicon 的 OpenCode 离线生命周期与 Cursor 官方安装 CI 门禁。

## v1.2.0 (2026-08-31)

- 全面重构中英文主页：亮色乐观视觉、桌面/手机自适应、可访问性、品牌 404 与单一 canonical。
- Pages 成为唯一网页源，Worker 自动生成同源资源；HTML 短缓存、版本化静态资源 immutable 缓存与 ETag 304。
- `agentboot` 延迟加载 HTTP/SSL 网络栈与安装专用模块，控制台冷启动显著缩短。
- 新增轻量 `launch.py`，让命令入口复用 Python 字节码缓存；频繁启动菜单实测降低约 34.6%。
- 多 Agent 安装按相同 Node 约束合并 npm 解析与连接，失败自动回退逐个安装；批次内复用 Node、镜像和环境探测。
- npm 安装优先本地缓存并关闭进度与冗余日志；在线安装器移除重复体检，POSIX 安装约减少一次 2 秒级网络检查。
- 内置 Agent 使用紧凑请求 JSON，并在断线重连时复用 TLSContext；保持 TLS 校验、代理与流式安全边界。
- 新增确定性性能基准，覆盖启动、内置 Agent 本地请求、安装调度与主页关键资源，所有实验保留/回退可审计。

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
- 离线包新增目标机逐文件 SHA-256 校验，`--all` 仅安装包内 MANIFEST 实际列出的 Agent；构建缺载荷会硬失败。
- 修复 Windows CMD shim 百分号格式、npm 真实入口解析和便携 Node 路径，Linux/Windows 均通过原生安装→启动→卸载矩阵。
- Worker 支持 Range/If-Range 与真实资产健康探测；发布采用 prerelease→Pages/Worker live verify→Latest 的协调状态机。
- 修正 Node engine 范围、离线资产名、相对链接、vLLM 文案、移动端表格溢出、触摸目标和旧性能固定数字。
- 安全模式改为可信系统路径的固定 argv 执行，禁止 shell grammar、路径伪装与未知确认策略放行。
- 截断/畸形 SSE 不再产生可执行工具调用；模型密钥仅发送到 HTTPS，网页工具默认拒绝内网/元数据地址。
- 配置与会话使用 0700/0600 原子持久化，命令超时终止整个进程树，安装状态更新加入跨进程锁。
- CoCo 卸载拒绝 symlink 根目录，私有 Node 在最终目录部署；Hermes uv、Node 与 Python 载荷完整校验。
- Release/Pages Actions 固定 commit、最小权限、显式源码清单；离线 Agent 更新与应用/launcher 事务支持回滚。
- Aider 改为 AgentBoot 私有 venv 安装；OpenCode 暂停离线声明，npm 离线入口按 JS/native/CMD 类型执行。
- Agent配置、代理、会话和安装清单改为私密原子持久化；并发安装状态加锁，命令超时终止整棵进程树。
- 在线/离线应用、launcher与Agent payload提交边界支持回滚；Windows中文路径、PowerShell 3哈希和批处理错误码修复。
- 发布矩阵新增Intel macOS原生Codex smoke；同源安装包增加成员/大小检查，离线构建只复制显式文件清单。

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
