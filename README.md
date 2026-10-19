# 简化中文技术写作 Skill

**保留原意，把中文技术文本写清楚。** 适用于工具描述、Agent 指令、错误信息、系统提示和技术文档。

A meaning-preserving Chinese technical writing skill, inspired by ASD-STE100.

[快速开始](#快速开始) · [改写示例](examples/before-after.md) · [Linter](references/linter.md) · [效果评估](evals/README.md) · [贡献指南](CONTRIBUTING.md)

## 看一个例子

**改前**

> 只有当上游任务已经完成且没有报错时，下游 Agent 才应该继续读取输出制品，但是超时的时候有时会产生部分制品。

**改后**

> 只有上游任务已完成且未报错时，下游 Agent 才应该继续读取输出制品。超时时，有时会产生部分制品。

改写保留了条件、完成状态、“应该”和“有时”。它不会把“可能失败”改成“失败”，也不会为一个含糊的“否则”擅自选择解释。[查看更多示例](examples/before-after.md)。

## 你会得到什么

- **一个写作 Skill**：让支持 Agent Skills 的助手按语义约束重写或审查中文。默认只返回改后文本，也可以要求解释改动。
- **一个可独立使用的 linter**：用 Python 标准库定位分号、长句和可疑表达。它只读文件，不调用模型，也不自动改写。
- **可审查的规则和案例**：说明何时简化、何时保留，以及如何比较不同版本的输出。

项目优先级是：**语义保真 > 指代和条件清晰 > 术语一致 > 句子简短**。目标是减少表达歧义；目前没有实验数据证明它能降低下游 Agent 的错误率。

本项目受 ASD-STE100 简化技术英语启发，是中文适配项目，不是官方中文版或合规认证工具。中文规则和 40 / 50 字预算均为本项目约定，详见[设计依据](references/writing-rules.md)。

## 快速开始

### 使用 npx 安装（推荐）

需要 Git、Node.js 和 npm。运行以下命令，按提示选择助手和安装范围：

```bash
npx skills add welkeyever/asd-ste100-skill-zh
```

默认安装到当前项目。若要安装到个人 Claude Code，供所有项目使用：

```bash
npx skills add welkeyever/asd-ste100-skill-zh \
  --skill asd-ste100-zh --agent claude-code --global --yes
```

只查看仓库中的 skill，不安装：

```bash
npx skills add welkeyever/asd-ste100-skill-zh --list
```

安装器直接从 GitHub 读取 skill，无需单独发布 npm 包。选项与环境要求以 [skills CLI 官方说明](https://github.com/vercel-labs/skills#readme)为准。本次验证使用的 `skills@1.7.2` 要求 Node.js ≥22.20.0。

### 使用 Git 手动安装

需要 Git。以下命令安装到个人 skills 目录，供所有项目使用：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/welkeyever/asd-ste100-skill-zh.git \
  ~/.claude/skills/asd-ste100-zh
```

如果只想在一个项目启用，将克隆目标改成该项目的 `.claude/skills/asd-ste100-zh`。[Claude Code 官方说明](https://code.claude.com/docs/en/skills)介绍了个人和项目级 skill 的加载方式。

### 第一次使用

安装后，在 Claude Code 中调用：

```text
/asd-ste100-zh

请重写下面的工具说明，只返回改后文本：
本工具可能会对返回结果进行检查，并在发现格式错误时发出通知。
```

一种符合规则的输出：

```text
本工具可能会检查返回结果，并在发现格式错误时发出通知。
```

这里保留同一句中的“可能会”，避免拆句时把通知动作变成无条件承诺。

### 其他助手与手动使用

本仓库使用 [Agent Skills 格式](https://agentskills.io/specification)。其他客户端应按各自说明安装整个目录，目录名使用 `asd-ste100-zh`，保留 `references/`、`examples/` 和 `scripts/` 的相对位置。未逐一验证各客户端的自动发现和调用行为。

不安装也可以把 [SKILL.md](SKILL.md) 作为写作指引，并把待改写文本交给助手。只使用写作指引时不需要 Python。

### 独立试用 linter

需要 Python 3.10+，无需安装依赖。在克隆的仓库目录运行：

```bash
printf '任务已启动；等待执行。\n' | python3 scripts/ste-lint-zh.py
```

这条示例会报告分号，退出码为 `1`。读取真实文件：

```bash
python3 scripts/ste-lint-zh.py --json path/to/doc.md
```

`path/to/doc.md` 替换成你要检查的 UTF-8 文件路径。退出码 `0` 表示硬检查未超过预算，`1` 表示超过，`2` 表示参数或输入错误。**退出码 `0` 不代表文本语义正确。**

## 如何使用

| 需求 | 提示示例 | 输出 |
|---|---|---|
| 直接重写 | 按简化中文规则重写这段工具说明 | 改后正文；必要时说明未解歧义 |
| 查看依据 | 重写这段 README，并解释改动 | 正文及原文 / 改后 / 理由表 |
| 只审查 | 检查这段 Agent 指令的歧义，先不改写 | 问题位置、原因和建议 |
| 约束术语 | 重写下面的说明，保留“租户”“工作区”和所有字段名 | 在这些约束内改写 |

操作步骤与接口说明默认使用**严格模式**，强调动作和条件。README 与解释性正文默认使用**偏意模式**，保留叙述节奏。两者都必须保留事实、情态、状态、范围和领域区别。

已有文本足够清楚时，默认原样返回。营销文案、文学创作和翻译不属于本项目的主要用途。

## Linter 能做什么

| 检查类型 | 行为 |
|---|---|
| 分号、句长、列表项悬挂连词 | 计入硬检查。可用 `--baseline N` 放宽数量预算，或 `--disable` 关闭某条规则 |
| 可疑黑话、修饰语、虚化动词、定语、术语变化、被动和体标记 | 仅建议，不影响退出码；需要结合上下文判断 |
| 事实、条件作用域、隐含主体、改写前后含义 | 无法验证，需要模型或人工复核 |

```bash
# 默认句长预算 50 字；操作说明可选 40 字
python3 scripts/ste-lint-zh.py --max-chars 40 instructions.md

# 容许存量的 3 条硬检查提示（数量预算，不是逐条豁免）
python3 scripts/ste-lint-zh.py --baseline 3 doc.md

# 关闭指定规则
python3 scripts/ste-lint-zh.py --disable noun-cluster,synonym-rotation doc.md
```

linter 跳过代码围栏、行内代码、文件开头的 YAML frontmatter 和 HTML 注释。它只支持部分 Markdown 结构，不是完整的语法解析器。规则 ID、JSON 字段、计数口径及限制见 [linter 说明](references/linter.md)。

## 如何判断有效

先检查**有没有改变含义**，再检查表达是否更清楚。不能用“字数更少”或“lint 全绿”证明改写有效。

- 脚本回归：`python3 -m unittest discover -s tests -v`
- 内置自检：`python3 scripts/ste-lint-zh.py --selftest`
- 改写效果：用[评估案例和方法](evals/README.md)比较开启 / 未开启 skill 的输出，记录模型、版本及语义差错。

GitHub Actions 配置会运行脚本自检和回归测试。模型改写效果需单独评估，目前未发布模型对照成绩。

## 文档与贡献

| 文件 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | 助手执行的改写规则与输出约定 |
| [规则设计依据](references/writing-rules.md) | 中文适配、取舍和来源 |
| [改写示例](examples/before-after.md) | 正常改写、保留原文、待澄清情况 |
| [贡献指南](CONTRIBUTING.md) | 报告误报、提交规则和验证改动 |
| [设计审查记录](docs/design-review.md) | 本轮问题、方案比较和实施范围 |

欢迎提交真实的误报、改写语义变化或难以理解的文档段落。请附最小输入、实际输出和期望含义；涉及内部资料时先匿名化。

## 来源与许可

基于 [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) 的结构和思路做中文适配，并参考 [ASD-STE100](https://www.asd-ste100.org/) 及中文技术写作资料。具体来源见 [CREDITS.md](CREDITS.md)。

代码与本仓库文档采用 [MIT License](LICENSE)，保留上游版权声明。引用的外部标准和资料适用各自许可。
