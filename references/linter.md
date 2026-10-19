# Linter 使用与接口

`scripts/ste-lint-zh.py` 只使用 Python 3.10+ 标准库。它扫描 UTF-8 文本，不调用模型、不修改文件。正则匹配是候选提示，不是语义证明。

## 命令

在仓库或已安装的 skill 目录运行：

```bash
python3 scripts/ste-lint-zh.py doc.md another.md
printf '本工具可能进行分析。\n' | python3 scripts/ste-lint-zh.py --json
python3 scripts/ste-lint-zh.py --max-chars 40 instructions.md
python3 scripts/ste-lint-zh.py --baseline 3 doc.md
python3 scripts/ste-lint-zh.py --disable noun-cluster,synonym-rotation doc.md
python3 scripts/ste-lint-zh.py --selftest
python3 scripts/ste-lint-zh.py --help
```

不传文件路径时读取 stdin。选项可位于文件路径之间。`--max-chars` 必须为正整数，`--baseline` 必须为非负整数，未知规则 ID 会报参数错误。

## 规则与级别

为兼容已有 JSON 使用者，保留 `advisory-free` 作为硬检查的级别名，`advisory` 表示建议。

| 规则 ID | 级别 | 含义与限制 |
|---|---|---|
| `semicolon` | 硬检查 | 正文中的中英文分号。是项目写作约定，不是中文语法错误 |
| `long-sentence` | 硬检查 | 超过 `--max-chars` 字符预算，默认 50。无法自动区分指令和描述 |
| `dangling-conjunction` | 硬检查 | 顶层列表项以“并 / 或 / 和 / 与 / 且”结束。正则可能误判以这些字结尾的专名 |
| `buzzword` | 建议 | 候选模糊词；字节对齐、网络链路等技术含义应保留 |
| `marketing-adjective` | 建议 | 检查修饰语是否有依据；不能为满足提示而补造数据 |
| `light-verb` | 建议 | 候选虚化动词结构；不将“完成”“发出”列为虚化动词 |
| `de-stacking` | 建议 | 多个“的”字短语；不能判断真实修饰关系 |
| `noun-cluster` | 建议 | 连续汉字及名词后缀；不等于已识别出 4 层名词 |
| `synonym-rotation` | 建议 | 同组词在文档共现；不证明它们指同一对象或动作 |
| `passive-voice` | 建议 | 候选“被”字结构；状态说明或未知施事者可保留 |
| `aspect-marker` | 建议 | 候选“正在…中”；不检查“已经…了” |

情态词本身不触发规则。包含“可能”的句子仍可因分号或超长而命中其他检查。脚本不自动统一术语或删除情态。

## 退出码与预算

- `0`：所有输入的硬检查总数不超过 `--baseline`，即使有建议也返回 `0`。
- `1`：硬检查总数超过预算。
- `2`：参数错误、文件不可读或输入解码错误。

`--baseline` 是总数预算，没有保存历史结果，也不会区分新旧问题。旧问题减少而新问题增加时，总数可能仍然通过。要针对某条规则做例外，用 `--disable`；当前不支持逐行豁免。不要为了零提示删除必要信息。

## JSON 契约

例如检查 `任务；继续。`：

```json
{
  "violations": [
    {
      "file": "<stdin>",
      "line": 1,
      "col": 3,
      "rule": "semicolon",
      "level": "advisory-free",
      "match": "；",
      "message": "本项目建议拆开分号连接的句子。保留条件与各分支的对应关系。"
    }
  ],
  "count": 1,
  "hard_count": 1,
  "baseline": 0,
  "chars": 6,
  "per_100_chars": 16.7
}
```

`line` 和 `col` 从 1 开始，列按原始文本的 Unicode 字符计数，不是 UTF-8 字节偏移或终端显示宽度。多文件按输入顺序汇总，文件内按行列排序。`violations` 的字段名为兼容旧版保留，其内容包含建议。`message` 是供人阅读的文案，程序应依赖 `rule` 和 `level`。

`count` 包含所有启用规则的提示；`hard_count` 只包含硬检查。`chars` 统计经过预处理的非空白字符，中文、ASCII 和标点均逐字符计数。它跳过代码等受保护区及识别到的标题、列表、引用前缀和表格分隔符。未识别的 Markdown 标记仍可能计入。`per_100_chars` 是提示密度，不是写作质量评分。关闭规则不会改变字符计数。

## Markdown 支持边界

支持同字符、足够长度的反引号和波浪号代码围栏，较长围栏中可以包含较短围栏。支持反引号数量匹配的行内代码、开头 YAML frontmatter、HTML 注释、普通表格、引用前缀和顶层列表。所有检查共用同一套代码屏蔽结果，保留原始行列位置。

跨物理行的正文合并计句长；空行、标题、列表项和表格单元格用于划分文本块。句末识别中文 `。！？`，以及后接空白或行末的英文 `.!?`。

这不是完整 CommonMark 解析器。缩进式代码块、复杂嵌套列表、链接目标、HTML 元素、强调标记和引用容器的特殊嵌套仍可能误报或漏报。Markdown 示例中的普通引用和表格会被检查；展示反例时可用代码块。不要把整个仓库的教学文档“lint 为零”当作发布门槛。

## 从 0.1 行为迁移

0.2 将依赖上下文的语言规则调整为建议，保持规则 ID、JSON 字段和退出码含义。原先仅因这些规则失败的 CI 现在可能返回 `0`。如果业务仍需要拦截某类建议，调用方可以按 JSON 的 `rule` 自行判断，但应先分析误报。

新增 `--max-chars` 允许显式设置句长预算。参数或文件错误统一返回 `2`。脚本不提供自动修复或语义评分。
