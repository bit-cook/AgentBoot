# DESIGN.md — AgentBoot

## 1. Objective

AgentBoot 的每个界面都应让人感到“工具已经准备好，下一步可以轻松开始”：明亮、可靠、有行动感，但不幼稚或喧闹。页面必须像一个经过认真编辑的开源工具，而不是套了营销模板的下载页；质量标准是可长期复用、可直接发布的产品级界面。

## 2. Product Context

- **What the product does:** AgentBoot 用一套可验证的安装流程，在 Linux、macOS 与 Windows 上按需安装、配置和卸载主流 AI Agent。
- **Who it's for:** 同时尝试多个命令行 AI Agent 的开发者与技术爱好者；他们会核对命令、来源和兼容性，希望快速开始，也在意安全边界与离线可用性。
- **Adjacent brands (feel like these):** Linear 的信息纪律、Vercel 文档的技术清晰度、Duolingo 的积极能量。
- **Distant brand (do not feel like this):** 远离典型 Web3 落地页；不使用霓虹渐变、漂浮光球和夸张承诺制造技术感。
- **Cultural register:** 技术可信为底，乐观亲切为表。像一个熟悉终端、愿意把复杂步骤收拾干净的朋友。

## 3. Visual Foundations

### 3a. Color

- **Neutral scale:** `--ink-950: #12251D`, `--ink-800: #294238`, `--ink-600: #5B7067`, `--ink-400: #91A198`, `--paper: #FFFDF5`, `--surface: #FFFFFF`, `--line: #DCE7DF`, `--soft: #F2F7F2`。
- **Accents:** `--green: #137A52` 为主要行动色，`--green-dark: #0D5E3E` 为悬停与高对比状态，`--sun: #FFD84D` 为乐观点睛色，`--coral: #FF7A59` 与 `--sky: #DFF3FF` 只用于结构提示。
- **Semantic:** `--success: #137A52`, `--warning: #A65E00`, `--error: #B42318`, `--info: #176B87`。
- **Usage rules:** 每个视口最多一个实心绿色主按钮；太阳黄承担品牌识别和视觉锚点，不承载小号正文；珊瑚色和天蓝色不得同时铺满大面积背景；正文永远使用中性色。

### 3b. Typography

- **Display face:** `ui-rounded, "Avenir Next Rounded", "SF Pro Rounded", "Segoe UI", sans-serif`，只使用 700 与 800，标题字距 `-0.035em`。
- **Body face:** `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`，使用 400、600、700。
- **Monospace:** `"SFMono-Regular", Consolas, "Liberation Mono", monospace`。
- **Type scale:** `12 / 14 / 16 / 18 / 24 / 32 / 48 / 72`，关键尺寸通过 `clamp()` 在相邻级别间平滑缩放。
- **Weight discipline:** 800 只用于 H1 和关键数字，700 用于 H2/H3，600 用于标签与按钮，正文保持 400；不得把整段说明设为半粗体。

### 3c. Spacing & rhythm

- **Base unit:** `4px`。
- **Spacing scale:** `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 / 128px`。
- **Generous whitespace:** 桌面端主章节垂直内边距为 `96–128px`，平板为 `72–96px`，手机为 `56–72px`；正文行宽不超过 `68ch`，全站容器不超过 `1180px`。

### 3d. Component seeds

- **Button:** 仅三类：绿色实心主操作、白底描边次操作、带方向箭头的文本链接。最小触控高度 `44px`，圆角 `12px`，不使用胶囊按钮。
- **Card / container:** 只在命令、安全说明和深度信息确实需要成组时使用；圆角 `18–24px`、1px 实线边框、无通用阴影。功能列表使用开放式分隔线，不做 3×2 卡片阵列。
- **Iconography:** 使用同一套 1.8px 圆角线性 SVG；图标只辅助动作或状态，不替代文字，不用 Emoji 作为装饰。
- **Brand mark:** 由太阳黄圆点和深绿色终端折线组成，表达“启动”和“向前”，可纯 CSS/SVG 重建。

## 4. Accessibility

- **Text contrast:** 正文至少 4.5:1，大字和 UI 至少 3:1；黄色不直接承载低字号文字。
- **Motion:** 动画只包含 160–420ms 的淡入、位移和状态反馈；`prefers-reduced-motion: reduce` 时关闭非必要动画与平滑滚动。
- **Focus indicators:** 所有可交互元素使用 `3px` 太阳黄外环加 `2px` 纸白间隔，不依赖颜色变化单独表达焦点。
- **Alt text policy:** 装饰性几何图形 `aria-hidden="true"`；信息图形必须用可见文本或准确的 `aria-label` 说明其状态和意义。
- **Interaction floor:** 触控目标至少 `44×44px`；命令行可键盘滚动，复制结果通过礼貌型 live region 通知；页面提供跳到主要内容的链接。

## 5. Voice & Tone

- **Register:** 对话式技术表达，明确但不生硬，积极但不喊口号。
- **Sentence rhythm:** 标题短而有动词；说明句长短混合，一段只传递一个判断。
- **Words this brand uses:** “装好”、“验证”、“按需”、“开始创造”。
- **Words this brand refuses:** “赋能”、“颠覆”、“无缝”、“革命性”、“解锁潜能”。
- **Address:** 中文优先使用省略主语的直接表达，必要时称“你”；英文使用 “you”，不称 “users”。

## 6. Implementation Practices

- **Token format:** 原生 CSS 自定义属性；静态页与 Worker 使用同一份 `pages/assets/site.css` 源文件。
- **Component convention:** 无框架、无运行时依赖的语义 HTML + 原生 CSS/JavaScript；任何浏览器脚本失效时，安装命令、链接和主要信息仍可使用。
- **Image treatment rules:** 不加载图库照片或 AI 位图；品牌表达来自排版、纯色几何和终端界面的代码原生图形。
- **Grid system:** 最大 12 列的流式 CSS Grid；主要采用不对称 `7:5` 首屏、`5:7` 安装区和内容重要性驱动的分栏，而不是等宽卡片矩阵。
- **Motion rules:** `cubic-bezier(.2,.8,.2,1)`，160–420ms；允许轻微上移、颜色和边框转换，禁止弹跳、无限漂浮和视差滚动。
- **Synchronization:** `pages/` 是中英文 HTML、CSS 与 JavaScript 的唯一视觉源；生成脚本把其内容嵌入 Worker，并以检查模式阻止多个线上入口漂移。

## 7. Anti-Patterns

- **No gradient hero backgrounds.** AgentBoot 的乐观感来自高明度纯色和清晰动作，不借用 SaaS 默认霓虹氛围。
- **No Emoji section headings.** 技术可信度由语言、排版和一致线性图形建立，不用聊天式符号凑气氛。
- **No 3×2 feature-card grid.** 功能按重要性分级，用开放式行列与一个重点模块表达，而不是把七项能力压成同样重量。
- **No primary button everywhere.** 首屏和当前安装动作各自只有一个主要视觉重心，其余操作使用描边或文本链接。
- **No empty superlatives.** 不写“强大、无缝、革命性”；每句价值陈述必须能由具体功能或发布验证支持。
- **No forced dark mode.** 用户明确要求亮色，视觉在不同系统主题下保持统一；高对比与夜间阅读通过色值质量解决，不自动翻转品牌。
- **No desktop shrink-down.** 手机布局重新排序、隐藏低价值表格列并扩大触控区，不只是把桌面内容缩小。

## 8. Decision-Making

1. **Accessibility is the floor.** 品牌色、布局或动效与可访问性冲突时，先改设计选择。
2. **Install clarity over visual novelty.** 安装命令、平台区别与安全说明不得为了构图被折叠或隐藏。
3. **One source over local perfection.** Worker、Pages 与镜像必须共享视觉源；不接受某个入口单独手工美化。
4. **Content hierarchy over completeness.** 核心价值先出现，深度能力后展开；同级信息过多时先合并语义，而不是再加卡片。
5. **Optimism over spectacle.** 色彩与微动效鼓励行动，但不抢占命令和文档的阅读注意力。
6. **Distinctive over generic.** 在不损害前五项的前提下，优先采用有 AgentBoot 识别度的结构，而非模板默认组件。

## 9. Workflow

1. 先写清每个页面唯一要完成的用户动作，并确认中英文信息对齐。
2. 用语义 HTML 排出阅读顺序，确保无 CSS/JavaScript 也能完成主要任务。
3. 应用颜色、字阶、空间与组件规则，保持每屏只有一个主要动作。
4. 从 `320px` 手机宽度开始布置，再扩展到平板、桌面和超宽屏。
5. 运行生成/同步检查，保证 Worker、Pages 与站点镜像没有内容漂移。
6. 用键盘、减少动态效果模式和高缩放检查交互与可读性。
7. 在真实浏览器中对中英文页面执行桌面、平板、手机截图和溢出检查。
8. 运行完整自动化测试与线上冒烟，确认安装分发端点未被视觉改动影响。
