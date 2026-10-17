# 简化中文技术写作 Skill — Simplified Chinese Technical Writing

一个把 **ASD-STE100 简化技术英语**（Simplified Technical English）的方法论迁移到中文的 Claude Code skill：**用一句一指令、短句、主动语态、术语一致、动作用动词**的方式，消除下游 agent / 翻译管线 / 非母语读者解析中文时的歧义。

这不是 ASD-STE100 的翻译版——英文的歧义来源（短语动词、现在完成时、第三人称 -s）和中文的歧义来源（"的"字堆叠、零主语、体标记混用、互联网黑话、中英混排）只有部分重叠。本 skill**替换**了不适用的英文规则、**新增**了中文独有的坑，详见 [`references/writing-rules.md`](references/writing-rules.md) 里的逐条决策说明。

## 为什么这件事值得做

ASD-STE100 的来源：航空维修手册的读者多数不是英文母语者，一条指令被误读在飞机上会死人。规则很直白——一词一义、主动语态、简单时态、一句一指令、不省主谓宾。

LLM Agent 消费另一个 Agent 的输出时处境极为相似：没有旁路、没法反问"你说的 X 是指 A 还是 B"。同一套规则，用来保护机务不误读扭矩规格的，拿来保护下游 agent 不误读工具描述、Agent 间指令、错误信息、系统提示——完全成立。

中文的工具描述、tool call 参数说明、系统 prompt 大面积塞满"进行 / 做出 / 发出" + 名词化的赘述、"的字" 堆叠的长定语、互联网黑话、以及中英混用的术语漂移。本 skill 正是打这些点。

## Before / After

| Before | After |
|---|---|
| "本工具会尝试在已经被配置的各个后端之间进行状态的同步，如果检测到冲突可能会根据已经设定好的策略来自动进行解决，否则会把冲突暴露出来以供人工审查。" | "本工具尝试同步已配置后端之间的状态。如果检测到冲突，工具按预设策略处理：允许自动解决时，工具可能自动解决冲突；不允许时，工具把冲突报告给人工审查。" |
| "由于预期的数据格式可能存在不匹配的问题，在处理您的请求的过程中可能发生了错误，这有可能是由于客户端版本过旧所引起的。" | "处理请求时可能发生了错误。原因可能是数据格式不符合服务端预期。过旧的客户端版本可能导致这种不匹配。请检查客户端版本。" |

更多例子（工具描述 / 错误信息 / Agent 间指令 / README 四类）见 [`examples/before-after.md`](examples/before-after.md)。

## 这个 Skill 做什么

1. **挑模式**。**严格模式**覆盖操作步骤、错误信息、Agent 间指令、工具描述。**偏意模式**覆盖 README、PR 描述、解释性正文——保留结构规则但放松术语严格一致。
2. **通读原文**理解在说什么。
3. **逐句过规则**。标出每条违反：虚化动词 + 名词化、"的"字堆叠、名词连用超限、禁分号、流水句、情态堆叠、互联网黑话、营销词、同义词轮换、体标记混用、句长超限、零主语歧义、被动语态滥用。
4. **逐句改写**——不改变原文事实、条件、作用域限定、情态强度。遇到简化会丢精度的地方，**保留较长说法并标记**，不默默简化。
5. **输出改后文本**——默认只输出结果，不加寒暄、不加模式声明、不加规则表。刻意保留的部分加一行 `保留原文:` 说明。

用户要规则表（"解释改了什么"/"diff"/"before/after"）时，输出命中规则的表格。

结构规则是机械可核的——你可以指着具体词或标点说"这里违反了哪条"。靠项目词表的规则（术语一致）标为建议而非强制。靠语感的规则（文体转换）不在 skill 范围内。

## 规则范围（和原 ASD-STE100 的区别）

| 原 ASD-STE100 规则 | 本 skill 处理 |
|---|---|
| 词汇规则（基于 ~900 词已批准词典） | **放弃词典依赖**——中文无一对一映射。保留"每次用同一个词 / 挑最常用的词"原则。 |
| 一词一义、术语一致 | **保留** |
| 动词形式优先于名词化（Rule 3.7） | **保留并强化**——中文版的"虚化动词 + 名词化"（"进行分析"/"完成部署"）比英文的 nominalization 更泛滥。 |
| 禁短语动词（Rule 9.3，如 "take off"） | **替换**——中文无短语动词，对应到"禁虚化动词 + 名词化"。 |
| 简单时态（禁 present perfect 等） | **替换**——中文无时态，对应到"体标记一致"（避免"正在…中"/"已经…了"）。 |
| 主动语态优先 | **保留并扩展**——中文除"被字句"外还有"受事主语句"（施事者缺失），都要防。 |
| 一句一指令 | **保留** |
| 句长 ≤ 20/25 词 | **换算成汉字**：指令 ≤ 40 字，描述 ≤ 50 字。 |
| 禁分号（Rule 8.1） | **保留** |
| 名词连用 ≤ 3 层 | **保留** |
| 禁省略 | **保留并强调**——中文允许零主语，agent-facing 文本不该省。 |
| 段 ≤ 6 句、流程用列表 | **保留** |
| （无） | **新增**："的"字堆叠（≥3 个"的"字短语堆到名词前） |
| （无） | **新增**：中英文术语二选一（同文档不混用 request/请求、server/服务器） |
| （无） | **新增**：互联网黑话过滤（赋能 / 打通 / 拉通 / 落地 / 对齐 / 下沉 / 复盘 / …） |
| （无） | **新增**：四字格 / 成语在技术文本里禁用（信息密度低、意义模糊） |

## 安装

### 克隆到项目 skills 目录

```bash
git clone https://github.com/<your-fork>/asd-ste100-skill-zh ~/.claude/skills/asd-ste100-zh
```

这会把 skill 装到 `~/.claude/skills/`，所有 Claude Code 项目都能用。

### npx skills（如发布到 skills.sh）

```bash
npx skills add <your-fork>/asd-ste100-skill-zh
```

## 用法

触发词（任选）：

```
把这段中文改一下让 agent 读不出歧义
应用简化中文规则到这段 prompt
plain Chinese 重写这段 tool description
中文消歧
受控中文改写
```

或者直接粘贴中文让 Claude："按简化中文重写" / "降低这段的歧义" / "按 asd-ste100-zh 改写"。

默认只返回改后文本。想看规则表加 "展示改动" / "diff 一下" / "解释改了什么"。

## Linter

`scripts/ste-lint-zh.py` 是不依赖任何外部库（Python 标准库 only）的结构规则 linter，覆盖：分号、句长（按汉字计）、虚化动词 + 名词化、"的"字堆叠、互联网黑话、营销词、名词连用、同义词轮换、体标记混用、被动语态、列表项悬挂连词。

```bash
# 单文件
python scripts/ste-lint-zh.py path/to/doc.md

# stdin
echo "本工具会尝试进行同步" | python scripts/ste-lint-zh.py

# JSON 输出
python scripts/ste-lint-zh.py --json doc.md

# 容忍存量违反
python scripts/ste-lint-zh.py --baseline 20 doc.md

# 关闭某些规则
python scripts/ste-lint-zh.py --disable passive-voice,noun-cluster doc.md

# 自检（验证"情态词永不触发"等底线）
python scripts/ste-lint-zh.py --selftest
```

**Linter 的限制**：

- 它是**正则驱动的启发式**，不是语法分析器。中文没有 POS tagging 做辅助时，`noun-cluster` 规则在长句里会把"X策略"/"Y平台"这类词当成名词簇后缀误触发。遇到误报用 `--disable noun-cluster` 关掉。
- `passive-voice` 规则是 `advisory`（建议级），永远不计入 `--baseline` 的硬违反数——因为中文的"被 X"合法用法太多，强推会伤真实有效的被动句。
- **情态词（可能 / 也许 / 或许 / 应该 / 会）永远不会被标记**——这是本 skill 的硬承诺，`--selftest` 把它写进断言。
- 本仓库自己的 SKILL.md 不 lint 干净，因为规则表引用了反例原文（"不应该"列）。用 `python scripts/ste-lint-zh.py --baseline 60 SKILL.md` 当"把 lint 结果读成示例"用。

## 范围

**适用场景**：Agent 间消息、工具/函数描述、错误信息、系统提示、Agent 间指令、tool call 参数说明——任何中文文本在没有人类消歧的情况下被机器或非母语读者解析的场景。

**不适用场景**：中文营销文案、文学文本、情绪宣传、品牌故事——简化中文规则刻意扁平化、去修辞化，用在这些地方会把文字改成技术手册的腔调。

一个重要前提：本 skill 修的是**形式**，不是**实质**。一段没内容的中文被改写后，还是一段短而干净的空话。

## 鸣谢（Credits）

本仓库受以下项目直接启发，谢意见 [CREDITS.md](CREDITS.md)：

- [`danyuchn/asd-ste100-skill`](https://github.com/danyuchn/asd-ste100-skill) — ASD-STE100 的原始英文 Claude Code skill，本仓库 fork 自此。
- [ASD-STE100 官方规范](https://www.asd-ste100.org/) — 底层方法论的来源。
- [`sparanoid/chinese-copywriting-guidelines`](https://github.com/sparanoid/chinese-copywriting-guidelines) — 中文文案排版指北，覆盖本 skill 不处理的排版细节。
- [`ruanyf/document-style-guide`](https://github.com/ruanyf/document-style-guide) — 阮一峰维护的中文技术文档写作规范。
- [`conorbronsdon/avoid-ai-writing`](https://github.com/conorbronsdon/avoid-ai-writing) — 同类英文 skill，启发了本仓库的"检测模式 + 评分"输出设计。

## 相关项目

- [`g4lb/asd-ste100-hebrew-skill`](https://github.com/g4lb/asd-ste100-hebrew-skill) — 希伯来语版 ASD-STE100 skill。
- [`meiluosi/rewrite-fidelity-skill`](https://github.com/meiluosi/rewrite-fidelity-skill) — 对比原文和改写版，标记含义和情态强度的变化。

## 协议

MIT — 见 [LICENSE](LICENSE)。保留 `danyuchn/asd-ste100-skill` 的原始 copyright。
