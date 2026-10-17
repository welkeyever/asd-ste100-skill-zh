# 鸣谢（Credits）

本仓库站在以下项目的肩膀上。按作用分类，每条说明**它贡献了什么**、**我们怎么借鉴**。

## 直接 fork 的上游

### [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill)

本仓库 fork 自此。英文版把 ASD-STE100 的 53 条规则压缩成一份面向 Claude Code 的可操作 skill，并写了一个纯标准库的 Python linter。

**我们借鉴了**：

- 整体文件结构（`SKILL.md` / `README.md` / `references/` / `examples/` / `scripts/`）。
- 两种模式（Strict / STE-flavored）的概念切分。
- 结构规则 vs 词汇规则的二分法——用来说明"哪些规则 skill 能自己核查、哪些需要项目词表"。
- Linter 的架构（规则表 + 正则 + selftest + baseline + disable）。
- **"情态词永不触发"的硬承诺**——这是原项目最有价值的设计洞察，中文版完整继承并在 selftest 里重写了对应断言。
- 输出格式契约（默认只输出改后文本，用户要规则表才给表）。

**我们没有继承的**：

- 原仓库的英文规则正则表达式（短语动词、现在完成时、分词歧义等）——中文不需要。
- 原仓库 README 里对 ASD 版权政策的详细讨论——我们在 `references/writing-rules.md` 里给了精简版。

License 保留 Dustin Yuchen Teng 的原始 copyright（MIT）。

## 底层方法论

### [ASD-STE100 官方规范](https://www.asd-ste100.org/)

Simplified Technical English 的定义者。本 skill 用的是其**原则**而非**词典**——原规范的 ~900 词已批准词典只定义英文、ASD 不允许自由转载。

- [About STE](https://www.asd-ste100.org/about_STE.html)
- [ASD Europe — Simplified Technical English](https://www.asd-europe.org/standards-specifications/simplified-technical-english/)
- [Wikipedia](https://en.wikipedia.org/wiki/Simplified_Technical_English)
- [TechScribe](https://www.techscribe.co.uk/techw/asd-simplified-technical-english.htm)
- [SKYbrary](https://skybrary.aero/articles/simplified-technical-english-ste)

需要官方规范时，到 [官方下载页](https://www.asd-ste100.org/STE_downloads.html) 请求（提交表单后邮件发链接）。

## 中文写作规范参考

### [sparanoid/chinese-copywriting-guidelines](https://github.com/sparanoid/chinese-copywriting-guidelines) — 中文文案排版指北

**15k+ stars 的事实标准**。覆盖中英文混排、全半角、数字空格、常用标点选择等**排版级**规则。本 skill 刻意**不**处理这些——它们已经被这份指南解决得很好，本 skill 聚焦于歧义修复，不越界。

**我们从中借鉴**：

- "中英文术语二选一"规则的灵感——指南长期强调中英文混排时的空格、全半角规范，本 skill 把它扩展到更高层：**同一文档内不混用同义中英术语**（避免 "request / 请求" 并存）。
- 对营销词、过度修辞的警觉。

### [ruanyf/document-style-guide](https://github.com/ruanyf/document-style-guide) — 中文技术文档的写作规范

**13k+ stars 的中文技术写作规范**。阮一峰长期维护。偏向文档写作的全局风格建议（段落结构、标题层级、术语使用、句式偏好）。

**我们从中借鉴**：

- 对"流水句"（长逗号串）的识别和拆句策略。
- 中文动名词化的典型例子（"进行 / 做出 / 完成 + 名词"结构）。
- 技术文档排版规范里的部分措辞倾向。

## 同类 skill（英文方向）

### [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing)

5k+ stars 的英文"去 AI 味"skill。49+ 条模式检测 + 0-100 评分 + CI 测试。和 `danyuchn/asd-ste100-skill` 在"重写 agent-facing 英文"这个窄类里是姊妹项目。

**我们从中借鉴**：

- "detect / rewrite / edit-in-place" 三模式输出的概念（本 skill 当前只实现"rewrite"，但为未来扩展留了余地）。
- 对**互联网黑话过滤**作为独立规则存在的信心——`avoid-ai-writing` 把它作为头号检查项，中文版同样把"赋能 / 打通 / 落地 / 对齐"等黑话列为硬违反。
- 规则表的组织方式（规则 ID + 级别 + 匹配模式 + 消息）。

### [andrewroxby/claude-style-patch](https://github.com/andrewroxby/claude-style-patch)

CLAUDE.md 风格补丁——约束 Claude prose 的常见坏习惯（标点、句式）。

**启发**：示范了"把一组写作建议直接写进项目的 CLAUDE.md"也是一条可用的路径。本仓库的 SKILL.md 的"扫查清单"部分吸收了类似的 "命名 + 示例 + 修法" 格式。

### [g4lb/asd-ste100-hebrew-skill](https://github.com/g4lb/asd-ste100-hebrew-skill)

希伯来语版 ASD-STE100 skill。证明了"ASD 原则可以适配到英语之外的语言"这件事可行。本中文版的做法和它方向相同——继承原则、重写规则、保留结构。

## 工具 / 代码启发

### [`meiluosi/rewrite-fidelity-skill`](https://github.com/meiluosi/rewrite-fidelity-skill)

对比原文和改写版、标记含义与情态变化的 skill。和本 skill 互补——本 skill 负责**改**，fidelity-skill 负责**审**改后是否没加没减原意。强烈推荐一起使用。

## 其他鸣谢

- Claude Code 团队的 Agent Skills 规范和模式（见 [`anthropics/skills`](https://github.com/anthropics/skills)），为本 skill 的 frontmatter 格式和触发机制提供了统一标准。
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) 的 "Writing & Prose Quality" 分类，帮助我们在立项时快速扫到同类项目。

## 没有鸣谢到谁？

如果本仓库在某个地方借鉴了你的工作而没有在此致谢，提 issue 或 PR 让我们补上。致谢应该是明确的、具体的，不是"受某处启发"的空话。
