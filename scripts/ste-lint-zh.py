#!/usr/bin/env python3
"""Dependency-free, heuristic checks for Chinese technical prose.

Scans surface patterns without a project dictionary. Deliberately never
flags modality markers (可能/也许/或许/应该/会): confidence is content, and a
linter that pressures modality out would rewrite claims.

Usage:
    ste-lint-zh.py FILE [FILE ...]
    echo "文本" | ste-lint-zh.py [--json]
    ste-lint-zh.py --baseline 5 FILE      # pass unless hard violations exceed 5
    ste-lint-zh.py --disable semicolon,passive-voice FILE
    ste-lint-zh.py --selftest

Exit 1 when hard ("advisory-free") violations exceed the baseline (default 0).
Context-dependent language findings are advisory and never fail the run.
Exit 2 on a usage error (unknown flag, bad value, unknown rule, unreadable file).
"""
import argparse
import bisect
import contextlib
import io
import json
import os
import re
import sys
import tempfile

# CJK range used by language heuristics, not by the character counter.
CJK = r"一-鿿"

# Modality markers that MUST NEVER be flagged. Keep this list stable; the selftest
# depends on it. Add to it carefully — any addition widens the "do not flag" surface.
MODALITY = ("可能", "也许", "或许", "大概", "应该", "可以", "会", "可能已经",
            "也许会", "或许会", "大概会", "应当", "将")

# Candidate jargon; many terms also have legitimate domain meanings.
BUZZWORDS = (
    "赋能", "打通", "拉通", "对齐", "下沉", "沉淀", "复盘",
    "抓手", "心智", "方法论", "生态位", "组合拳", "底座", "链路",
    "闭环", "触达", "转化率提升", "转化率", "提效", "降本增效",
    "战略级", "顶层设计", "顶层",
)

# Marketing adjectives — the Chinese equivalents of "seamless / robust / cutting-edge".
MARKETING_ADJECTIVES = (
    "无缝", "极致", "丝滑", "全新", "全方位", "一站式", "开箱即用",
    "业界领先", "行业领先", "业内领先", "业内首创", "首屈一指",
    "颠覆性", "革命性", "划时代", "里程碑式", "现象级",
)

# Candidate "light verb + noun" patterns.
# Format: light verb followed by (optional "的", "一个", etc.) and a nominalized action noun.
# The intervening text is not parsed; all matches need contextual review.
# 完成 carries completion, and 发出 can distinguish sending from receiving.
# Neither is safe to treat as a filler verb.
LIGHT_VERBS = ("进行", "做出", "开展", "实施", "展开",
               "作出", "给予", "予以", "加以")
# Suffixes marking nominalized actions in Chinese.
NOMINALIZED_SUFFIXES = ("分析", "处理", "部署", "优化", "检查", "审核", "审查",
                       "验证", "确认", "设计", "实现", "开发", "测试", "评估",
                       "调研", "调查", "沟通", "交流", "协作", "合作", "决策",
                       "判断", "通知", "报告", "汇报", "总结", "思考", "探索",
                       "调整", "修改", "更新", "升级", "监控", "告警", "通信",
                       "交互", "重构", "改造", "回滚", "回归", "发布", "上线",
                       "下线", "运维", "操作", "管控", "管理", "治理", "整合")
LIGHT_VERB_PATTERN = re.compile(
    r"(" + "|".join(LIGHT_VERBS) + r")"
    r"(?:一个|一次|这个|那个|其|此|一下)?"
    r"(?:[" + CJK + r"]{0,6}?)"
    r"(" + "|".join(NOMINALIZED_SUFFIXES) + r")"
)

# Passive voice markers in Chinese. Beyond "被", also "由 X 完成/处理" and "受 X 影响".
# This is heuristic — Chinese passive is messy. We only flag "被 + verb" conservatively,
# because 由/受 constructions are often legitimate.
PASSIVE_MARKER = re.compile(
    r"被(?:[" + CJK + r"]{1,3})?"
    r"(" + "|".join(NOMINALIZED_SUFFIXES) + r"|删除|执行|调用|启动|停止|触发|创建|关闭)"
)

# Possible aspect-marker redundancy. Natural "已经 X 了" is not a target.
ASPECT_REDUNDANCY = [
    (re.compile(r"正在[" + CJK + r"]{1,6}?中(?=[，。！？\s]|$)"),
     "正在…中", "可能重复表达进行状态。确认 '中' 是状态标记后再简化，保留动作状态。"),
]

# Chinese "的" stacking: three or more "X 的" phrases before a single noun.
# Heuristic: match "X的Y的Z的W" where X/Y/Z are 1–8 CJK chars.
DE_STACK = re.compile(
    r"(?:[" + CJK + r"a-zA-Z0-9]{1,8}的){3,}"
)

# Candidate long noun phrase: this regex cannot identify nouns or count layers.
NOUN_CLUSTER = re.compile(
    r"[" + CJK + r"]{4,}(?:器|层|模块|服务|组件|引擎|中心|平台|系统|协议|流程|策略)"
)

# Semicolons: both ASCII (;) and fullwidth (；), a local writing convention.
SEMICOLON = re.compile(r"[;；]")

# Candidate terms only: co-occurrence cannot establish referential identity.
SYNONYM_GROUPS = [
    ("用户", "客户", "使用者", "操作员"),       # the human
    ("检查", "校验", "核对", "审核"),             # inspect
    ("删除", "移除", "清除"),                      # delete
    ("启动", "开启", "打开", "启用"),             # start
    ("停止", "关闭", "终止"),                      # stop
    ("显示", "展示", "呈现"),                      # show
    ("使用", "调用", "利用"),                      # use
    ("修复", "修正", "修理"),                      # fix
    ("发送", "传输", "推送"),                      # send
    ("获取", "拉取", "读取", "取回"),             # may refer to different operations
    ("更改", "修改", "调整"),                      # change
    ("请求", "调用", "访问"),                      # request (note: 调用 also in 使用 group — that is OK, both groups flag it)
]

# Project-local character budgets, not an English-to-Chinese conversion.
MAX_CHARS_DESCRIPTIVE = 50
# Instruction text can explicitly select a 40-character budget via --max-chars.

RULES = [
    ("semicolon", "advisory-free",
     SEMICOLON,
     "本项目建议拆开分号连接的句子。保留条件与各分支的对应关系。"),
    ("buzzword", "advisory",
     re.compile("(" + "|".join(BUZZWORDS) + ")"),
     "可能是模糊用语。若为领域术语（如字节对齐、网络链路），保留。"),
    ("marketing-adjective", "advisory",
     re.compile("(" + "|".join(MARKETING_ADJECTIVES) + ")"),
     "检查修饰语是否提供具体信息。只使用原文已有的事实，不补造数据。"),
    ("light-verb", "advisory",
     LIGHT_VERB_PATTERN,
     "可能有虚化动词。确认不改变动作、状态和情态后再简化。"),
    ("de-stacking", "advisory",
     DE_STACK,
     "可能有 '的' 字堆叠。确认修饰关系难以理解时再拆句，保留原来的修饰范围。"),
    ("noun-cluster", "advisory",
     NOUN_CLUSTER,
     "可能有过长定语或复合名词。此正则不能判断名词层数，请结合领域含义复核。"),
    ("passive-voice", "advisory",
     PASSIVE_MARKER,
     "可能的被动语态。改成主动句，除非施事者未知或无关。"),
]


CODE_FENCE = re.compile(r"^\s*(?P<run>`{3,}|~{3,})(?P<tail>.*)$")
# A sentinel preserves offsets and prevents a code-ending list item from being
# mistaken for a dangling conjunction. It is excluded from character counts.
MASK = "\ufffc"
# List markers: Markdown unordered (-/*/+) and numeric (1./1)/1、). Chinese ordinal 1、 is common.
LIST_ITEM_START = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>[-*+]|[0-9]+[.)、])(?P<gap> +)(?P<body>.*)$"
)
CONJUNCTION_END = re.compile(r"(?:并|或|和|与|且)\s*$")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
STANDALONE_LINE = re.compile(r"^ {0,3}(?:#|<|(?:[-*_=] *){3,}$)")
BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}(?:> ?)+")
ANY_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|[0-9]+[.)、])(?:\s|$)")


def _char_count(text):
    """Count non-space, non-masked Unicode code points, including punctuation."""
    return sum(1 for c in text if not c.isspace() and c != MASK)


def _mask(text):
    return "".join(c if c.isspace() else MASK for c in text)


def _prose_lines(text):
    """Mask non-prose once for every rule, preserving source line/column offsets.

    Supports backtick/tilde fences (including longer outer fences), inline code
    with matching delimiter lengths, leading YAML frontmatter and HTML comments.
    This is intentionally a Markdown subset, not a full CommonMark parser.
    """
    lines = text.splitlines(keepends=True)
    fence = None
    inline_end = None
    in_comment = False
    offset = 0
    frontmatter = bool(lines and lines[0].strip() == "---"
                       and any(line.strip() in ("---", "...") for line in lines[1:]))
    for index, line in enumerate(lines):
        line_offset = offset
        offset += len(line)
        if frontmatter:
            lines[index] = _mask(line)
            if index and line.strip() in ("---", "..."):
                frontmatter = False
            continue
        quote = BLOCKQUOTE_PREFIX.match(line)
        content = line[quote.end():] if quote else line
        match = CODE_FENCE.match(content.rstrip("\r\n"))
        if fence:
            lines[index] = _mask(line)
            if (match and match['run'][0] == fence[0]
                    and len(match['run']) >= fence[1] and not match['tail'].strip()):
                fence = None
            continue
        if (not in_comment and inline_end is None and match
                and not (match['run'][0] == '`' and '`' in match['tail'])):
            fence = (match['run'][0], len(match['run']))
            lines[index] = _mask(line)
            continue

        # Walk inline code and comments in source order. Delimiters inside one
        # protected region must not open a different region and hide later prose.
        masked = list(line)
        cursor = 0
        while cursor < len(line):
            if in_comment:
                closing = line.find('-->', cursor)
                end = closing + 3 if closing >= 0 else len(line)
                masked[cursor:end] = _mask(line[cursor:end])
                in_comment = closing < 0
                cursor = end
            elif inline_end is not None:
                closing = inline_end.search(line, cursor)
                end = closing.end() if closing else len(line)
                masked[cursor:end] = _mask(line[cursor:end])
                if closing:
                    inline_end = None
                cursor = end
            else:
                token = re.search(r'<!--|`+', line[cursor:])
                if not token:
                    break
                start, end = cursor + token.start(), cursor + token.end()
                if token.group() == '<!--':
                    in_comment = True
                    cursor = start
                else:
                    delimiter = re.compile(r'(?<!`)' + re.escape(token.group()) + r'(?!`)')
                    # An unmatched opening run is literal prose, not code.
                    if delimiter.search(text, line_offset + end):
                        inline_end = delimiter
                        masked[start:end] = _mask(line[start:end])
                    cursor = end
        lines[index] = ''.join(masked)
    return ''.join(lines).splitlines()


def _sentence_starts(text):
    """Return Unicode character offsets where sentences start.

    Chinese sentences end at 。！？. ASCII .!? also end a sentence when followed
    by whitespace or end-of-string. Returns a list of start offsets.
    """
    if not text.strip():
        return [0]
    starts = [0]
    enders = set("。！？")
    i = 0
    while i < len(text):
        c = text[i]
        if c in enders:
            # Chinese ender always ends a sentence
            j = i + 1
            while j < len(text) and text[j] in "\"'”’)]":
                j += 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text):
                starts.append(j)
            i = j
            continue
        if c in ".!?":
            # ASCII ender: only if followed by whitespace or end
            j = i + 1
            while j < len(text) and text[j] in "\"'”’)]":
                j += 1
            if j >= len(text) or text[j].isspace():
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text):
                    starts.append(j)
                i = j
                continue
        i += 1
    return starts


def _long_sentence_findings(pieces, filename, max_chars):
    """Flag long sentences in one prose block.

    pieces is a list of (lineno, source_column, text) tuples. The texts are
    joined with spaces, so a sentence wrapped across lines counts once.
    """
    if not pieces:
        return []
    offsets, position = [], 0
    for _, _, text in pieces:
        offsets.append(position)
        position += len(text) + 1
    joined = " ".join(text for _, _, text in pieces)
    findings = []
    starts = _sentence_starts(joined)
    for start, end in zip(starts, starts[1:] + [len(joined)]):
        n = _char_count(joined[start:end])
        if n <= max_chars:
            continue
        index = bisect.bisect_right(offsets, start) - 1
        offset = offsets[index]
        lineno, source_column, _ = pieces[index]
        findings.append({"file": filename, "line": lineno,
                         "col": source_column + start - offset + 1,
                         "rule": "long-sentence", "level": "advisory-free",
                         "match": f"{n} 字",
                         "message": f"句子长 {n} 字（预算 {max_chars} 字）。可拆句，但须保留条件、例外和作用域。"})
    return findings


def _leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


def _is_list_continuation(line, content_indent):
    if not line.strip():
        return True
    if LIST_ITEM_START.match(line):
        return False
    return _leading_spaces(line) >= content_indent


def _split_table_row(line):
    """Trimmed table cells and their zero-based source columns."""
    left = len(line) - len(line.lstrip())
    right = len(line.rstrip())
    content = line[left:right]
    if "|" not in content:
        return None
    if content.startswith("|"):
        content = content[1:]
        left += 1
    if content.endswith("|"):
        content = content[:-1]
    raw_cells = re.split(r"(?<!\\)\|", content)
    if len(raw_cells) < 2:
        return None
    cells = []
    column = left
    for raw_cell in raw_cells:
        leading = len(raw_cell) - len(raw_cell.lstrip())
        cells.append((raw_cell.strip(), column + leading))
        column += len(raw_cell) + 1
    return cells


def _markdown_table_cells(lines):
    """Map ordinary Markdown table rows to their prose cells."""
    table_cells = {}
    index = 1
    while index < len(lines):
        separator = _split_table_row(lines[index])
        header = _split_table_row(lines[index - 1])
        if (not separator or not header or len(separator) != len(header)
                or not all(TABLE_SEPARATOR_CELL.fullmatch(cell)
                           for cell, _ in separator)):
            index += 1
            continue
        table_cells[index - 1] = header
        table_cells[index] = []
        index += 1
        while index < len(lines):
            row = _split_table_row(lines[index])
            if not row or len(row) != len(separator):
                break
            table_cells[index] = row
            index += 1
    return table_cells


def _dangling_conjunction_findings(lines, filename, source_lines):
    """List items that end with 并/或/和/与/且."""
    findings = []
    index = 0
    while index < len(lines):
        line = lines[index]
        start = LIST_ITEM_START.match(line)
        if not start:
            index += 1
            continue
        content_indent = (len(start.group("indent"))
                          + len(start.group("marker"))
                          + len(start.group("gap")))
        item_lines = [(index, start.group("body"))]
        next_index = index + 1
        while next_index < len(lines):
            candidate = lines[next_index]
            if not _is_list_continuation(candidate, content_indent):
                break
            item_lines.append((next_index, candidate))
            next_index += 1
        meaningful = []
        for line_index, item_line in item_lines:
            cleaned = item_line.strip()
            if cleaned:
                meaningful.append((line_index, cleaned))
        if meaningful:
            end_line_index, end_line = meaningful[-1]
            conjunction = CONJUNCTION_END.search(end_line)
        else:
            end_line_index, end_line, conjunction = None, None, None
        if conjunction:
            if end_line_index == index:
                finding_line = index + 1
                finding_col = start.start("marker") + 1
            else:
                raw_end_line = next(
                    raw for line_index, raw in item_lines
                    if line_index == end_line_index
                )
                raw_conjunction = CONJUNCTION_END.search(raw_end_line)
                finding_line = end_line_index + 1
                finding_col = raw_conjunction.start() + 1 if raw_conjunction else 1
            findings.append({
                "file": filename,
                "line": finding_line,
                "col": finding_col,
                "rule": "dangling-conjunction",
                "level": "advisory-free",
                "match": source_lines[end_line_index][start.start('body'):].strip()
                         if end_line_index == index else source_lines[end_line_index].strip(),
                "message": "列表项以连词（并/或/和/与/且）结尾。补完此项，或与下一项合并。",
            })
        index = next_index
    return findings


def _aspect_redundancy_findings(line, lineno, source_column, filename):
    """Advisory candidates for repeated progressive-state markers."""
    findings = []
    for pattern, label, msg in ASPECT_REDUNDANCY:
        for m in pattern.finditer(line):
            findings.append({
                "file": filename, "line": lineno,
                "col": source_column + m.start() + 1,
                "rule": "aspect-marker", "level": "advisory",
                "match": m.group(0),
                "message": msg,
            })
    return findings


def _is_modality_context(text, pos):
    """Return True if the match at `pos` is actually a modality marker that must not be flagged.

    This is the hard safety rail: anywhere a modality word spans the match, skip the finding.
    """
    for marker in MODALITY:
        # Check if marker overlaps with the match position
        for m in re.finditer(re.escape(marker), text):
            if m.start() <= pos < m.end():
                return True
    return False


def lint(text, filename="<stdin>", max_chars=MAX_CHARS_DESCRIPTIVE):
    findings = []
    chars_total = 0
    lines = _prose_lines(text)
    table_cells = _markdown_table_cells(lines)
    seen_synonyms = {}  # (group_idx, base) -> (line, col, match)
    block = []
    in_quote = False

    def flush():
        findings.extend(_long_sentence_findings(block, filename, max_chars))
        block.clear()

    for lineno, raw_line in enumerate(lines, 1):
        if raw_line and all(c.isspace() or c == MASK for c in raw_line):
            flush()
            continue
        segments = table_cells.get(lineno - 1, [(raw_line, 0)])
        is_table = (lineno - 1) in table_cells
        quote = BLOCKQUOTE_PREFIX.match(raw_line)
        is_quote = bool(quote)
        content = raw_line[quote.end():] if quote else raw_line
        standalone = STANDALONE_LINE.match(content)
        if (is_table or not content.strip() or standalone
                or ANY_LIST_ITEM.match(content) or is_quote != in_quote):
            flush()
        in_quote = is_quote

        for segment, source_column in segments:
            line = segment
            if not is_table:
                prefix = BLOCKQUOTE_PREFIX.match(line)
                if prefix:
                    source_column += prefix.end()
                    line = line[prefix.end():]
                prefix = re.match(r"\s*(?:#{1,6}\s+|(?:[-*+]|[0-9]+[.)、])\s+)", line)
                if prefix:
                    source_column += prefix.end()
                    line = line[prefix.end():]
            chars_total += _char_count(line)

            for rule_id, level, pattern, msg in RULES:
                for m in pattern.finditer(line):
                    # modality safety rail
                    if _is_modality_context(line, m.start()):
                        continue
                    findings.append({
                        "file": filename, "line": lineno,
                        "col": source_column + m.start() + 1,
                        "rule": rule_id, "level": level,
                        "match": m.group(0), "message": msg,
                    })

            findings.extend(_aspect_redundancy_findings(
                line, lineno, source_column, filename
            ))

            for gi, group in enumerate(SYNONYM_GROUPS):
                for base in group:
                    if (gi, base) in seen_synonyms:
                        continue
                    pos = line.find(base)
                    if pos >= 0:
                        seen_synonyms[(gi, base)] = (
                            lineno, source_column + pos + 1, base
                        )

            if line.strip():
                block.append((lineno, source_column, line))
            if is_table:
                flush()
        if standalone:
            flush()
    flush()

    # synonym rotation: flag each member after the first, at its first occurrence
    for gi, group in enumerate(SYNONYM_GROUPS):
        present = [(seen_synonyms[(gi, b)], b) for b in group if (gi, b) in seen_synonyms]
        if len(present) > 1:
            present.sort()
            first_base = present[0][1]
            for (lineno, col, match), base in present[1:]:
                findings.append({
                    "file": filename, "line": lineno, "col": col,
                    "rule": "synonym-rotation", "level": "advisory",
                    "match": match,
                    "message": f"'{base}' 和 '{first_base}' 同时出现。仅在确认指同一对象、同一动作时统一，保留领域区别。",
                })

    findings.extend(_dangling_conjunction_findings(lines, filename, text.splitlines()))
    findings.sort(key=lambda f: (f["line"], f["col"]))
    return findings, chars_total


def report(findings, chars_total, as_json, hard_count, baseline):
    rate = round(len(findings) * 100 / chars_total, 1) if chars_total else 0.0
    if as_json:
        print(json.dumps({"violations": findings, "count": len(findings),
                          "hard_count": hard_count, "baseline": baseline,
                          "chars": chars_total, "per_100_chars": rate},
                         indent=2, ensure_ascii=False))
        return
    for f in findings:
        print(f"{f['file']}:{f['line']}:{f['col']} {f['rule']} ({f['level']}): {f['message']} [{f['match']}]")
    print(f"\n{len(findings)} 条提示（硬检查 {hard_count}，基线 {baseline}），"
          f"共 {chars_total} 字，每百字 {rate} 处。")
    print("提示数量不是质量评分。情态词本身不触发规则，改写仍需人工或模型复核语义。")


def selftest():
    """The hard safety rails live here. If any assertion fails, this script is broken."""

    # 1. Modality markers must never be flagged. This is the headline promise.
    #    Includes modal + aspect ("可能已经失败"), which is the Chinese equivalent of
    #    "may have failed" in the English skill.
    text = "本工具可能已经失败。原因可能是超时。磁盘也许已经满了。或许需要重试。"
    findings, _ = lint(text)
    assert not findings, f"Modality got flagged: {findings}"

    # 2. Buzzwords get flagged.
    text = "通过底座能力赋能上层业务，一站式打通数据链路。"
    findings, _ = lint(text)
    rules = {f["rule"] for f in findings}
    assert "buzzword" in rules, findings
    assert "marketing-adjective" in rules, findings

    # 3. Light verb + nominalization gets flagged.
    text = "对日志进行分析。开展服务测试。做出判断。"
    findings, _ = lint(text)
    light = [f for f in findings if f["rule"] == "light-verb"]
    assert len(light) >= 3, light

    # 4. "的" stacking gets flagged.
    text = "一个基于最新的 AI 技术的用于处理用户的请求的服务。"
    findings, _ = lint(text)
    de = [f for f in findings if f["rule"] == "de-stacking"]
    assert de, findings

    # 5. Semicolon gets flagged (both fullwidth and halfwidth).
    for sep in ("；", ";"):
        findings, _ = lint(f"任务已启动{sep}等待执行")
        assert any(f["rule"] == "semicolon" for f in findings), (sep, findings)

    # 6. Semicolon inside code block is skipped.
    findings, _ = lint("```\nx = 1; y = 2\n```")
    assert not findings, findings

    # 7. Synonym rotation gets flagged.
    text = "检查配置文件。校验输出。审核返回值。"
    findings, _ = lint(text)
    rot = [f for f in findings if f["rule"] == "synonym-rotation"]
    assert len(rot) >= 2, rot
    assert "'校验' 和 '检查'" in rot[0]["message"] or "'审核' 和 '检查'" in rot[0]["message"], rot

    # 8. Single consistent term: no flag.
    findings, _ = lint("检查配置。检查输出。")
    assert not any(f["rule"] == "synonym-rotation" for f in findings)

    # 9. Long sentence (>50 chars) gets flagged.
    long_text = "这是" + "一个很长的子句，" * 10 + "最后结束。"
    findings, _ = lint(long_text)
    assert any(f["rule"] == "long-sentence" for f in findings), findings

    # 10. Short sentences do NOT get flagged.
    findings, _ = lint("短句。另一短句。")
    assert not any(f["rule"] == "long-sentence" for f in findings), findings

    # 11. Dangling conjunction (并/或/和/与/且) in list items.
    text = (
        "- 设定目标并\n"
        "- 记录结果或\n"
        "- 关闭面板"
    )
    findings, _ = lint(text)
    dangling = [f for f in findings if f["rule"] == "dangling-conjunction"]
    assert len(dangling) == 2, dangling
    assert [f["line"] for f in dangling] == [1, 2], dangling

    # 12. Dangling conjunction inside fenced code is ignored.
    findings, _ = lint("~~~\n- 代码并\n~~~")
    assert not any(f["rule"] == "dangling-conjunction" for f in findings)

    # 13. Aspect-marker redundancy.
    findings, _ = lint("任务正在启动中。")
    assert any(f["rule"] == "aspect-marker" for f in findings), findings

    # 14. Passive voice heuristic flags "被 X" but is advisory.
    findings, _ = lint("文件被用户删除。")
    passive = [f for f in findings if f["rule"] == "passive-voice"]
    assert passive, findings
    assert passive[0]["level"] == "advisory", passive

    # 15. Modality + perfect-looking phrase is NOT a passive. "可能已经失败" must stay clean.
    findings, _ = lint("请求可能已经失败。")
    assert not findings, findings

    # 16. Noun cluster of 4+ CJK before a noun-suffix gets flagged.
    findings, _ = lint("用户任务队列处理器。")
    assert any(f["rule"] == "noun-cluster" for f in findings), findings

    # 17. Baseline flag controls exit code (tested in main-level selftest).
    #     Here we verify disable works: silencing a rule removes its findings.
    text = "通过赋能业务打通链路。"
    findings, _ = lint(text)
    assert any(f["rule"] == "buzzword" for f in findings)
    # Simulate --disable buzzword
    filtered = [f for f in findings if f["rule"] != "buzzword"]
    assert not any(f["rule"] == "buzzword" for f in filtered)

    # 18. Per-file labels propagate.
    findings, _ = lint("可能；", filename="x.md")
    assert findings[0]["file"] == "x.md"

    # 19. Inline code is masked, not deleted; columns stay true.
    findings, _ = lint("运行 `make all` 然后使用赋能框架。")
    buzz = [f for f in findings if f["rule"] == "buzzword"]
    assert len(buzz) == 1, buzz
    # column should point at the buzzword, past the code span
    assert buzz[0]["col"] >= 15, buzz

    # 20. Markdown table cells are each their own prose block.
    short_cell = "这是短单元格。"
    long_cell = "这是" + "一段很长的内容，" * 8 + "结束。"
    findings, _ = lint(
        f"| 标签 | 详情 |\n| --- | --- |\n| 清晰 | {long_cell} |"
    )
    long_sentences = [f for f in findings if f["rule"] == "long-sentence"]
    assert len(long_sentences) == 1, long_sentences

    # 21. Command-line parsing rejects typos and bad values.
    for bad in (["--basline", "3"], ["--baseline"], ["--baseline", "x"],
                ["--baseline", "-1"], ["--disable", "passive"],
                ["--disable", "nonexistent"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(bad)
        except SystemExit as e:
            assert e.code == 2, (bad, e.code)
        else:
            raise AssertionError(bad)

    # 22. --disable accepts known rules.
    assert _rule_list("semicolon,buzzword") == {"semicolon", "buzzword"}

    # 23. Flags can appear between file paths (intermixed parsing).
    with tempfile.TemporaryDirectory() as tmp:
        paths = [os.path.join(tmp, name) for name in ("a.md", "b.md")]
        for path in paths:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("短句。\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert main([paths[0], "--json", paths[1]]) == 0
        data = json.loads(out.getvalue())
        assert data["chars"] == 6, out.getvalue()

    print("selftest OK")


RULE_IDS = {rule_id for rule_id, *_ in RULES} | {
    "long-sentence", "synonym-rotation", "dangling-conjunction", "aspect-marker"}


def _rule_list(value):
    rules = {r for r in value.split(",") if r}
    unknown = rules - RULE_IDS
    if unknown:
        raise argparse.ArgumentTypeError(
            f"未知规则: {', '.join(sorted(unknown))}。已知: {', '.join(sorted(RULE_IDS))}"
        )
    return rules


def _non_negative_int(value):
    try:
        n = int(value)
    except ValueError:
        n = -1
    if n < 0:
        raise argparse.ArgumentTypeError(f"需要非负整数，得到 {value!r}")
    return n


def _positive_int(value):
    n = _non_negative_int(value)
    if n == 0:
        raise argparse.ArgumentTypeError("需要正整数")
    return n


def main(argv):
    parser = argparse.ArgumentParser(
        prog="ste-lint-zh.py", allow_abbrev=False,
        description="中文简化写作结构规则的确定性 linter。未传 FILE 时读取 stdin。")
    parser.add_argument("paths", nargs="*", metavar="FILE")
    parser.add_argument("--json", action="store_true", help="按 JSON 输出")
    parser.add_argument("--baseline", type=_non_negative_int, default=0, metavar="N",
                        help="允许 N 条硬违反（默认 0）")
    parser.add_argument("--disable", type=_rule_list, default=set(), metavar="RULES",
                        help="逗号分隔的规则 ID，关闭这些检查")
    parser.add_argument("--selftest", action="store_true", help="运行内置测试")
    parser.add_argument("--max-chars", type=_positive_int, default=MAX_CHARS_DESCRIPTIVE,
                        metavar="N", help="句长预算（默认 50，指令文本可选 40）")
    args = parser.parse_intermixed_args(argv)
    if args.selftest:
        selftest()
        return 0
    as_json, baseline, disabled, paths = args.json, args.baseline, args.disable, args.paths

    findings, chars_total = [], 0
    if paths:
        for p in paths:
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeError) as e:
                parser.error(f"无法读取 UTF-8 文件 {p}: {e}")
            f, w = lint(text, filename=p, max_chars=args.max_chars)
            findings.extend(f)
            chars_total += w
    else:
        try:
            text = (sys.stdin.buffer.read().decode("utf-8")
                    if hasattr(sys.stdin, "buffer") else sys.stdin.read())
            findings, chars_total = lint(text, max_chars=args.max_chars)
        except (OSError, UnicodeError) as e:
            parser.error(f"无法读取 UTF-8 输入: {e}")

    findings = [f for f in findings if f["rule"] not in disabled]
    hard_count = sum(1 for f in findings if f["level"] == "advisory-free")
    report(findings, chars_total, as_json, hard_count, baseline)
    return 1 if hard_count > baseline else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
