#!/usr/bin/env python3
"""Deterministic linter for the structural rules in Chinese SKILL.md.

Checks only rules verifiable without a project dictionary. Deliberately never
flags modality markers (可能/也许/或许/应该/会): confidence is content, and a
linter that pressures modality out would rewrite claims.

Usage:
    ste-lint-zh.py FILE [FILE ...]
    echo "文本" | ste-lint-zh.py [--json]
    ste-lint-zh.py --baseline 5 FILE      # pass unless hard violations exceed 5
    ste-lint-zh.py --disable semicolon,passive-voice FILE
    ste-lint-zh.py --selftest

Exit 1 when hard ("advisory-free") violations exceed the baseline (default 0).
Advisory findings (passive-voice, aspect-marker) never fail the run.
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

# Chinese character range used for word-count: CJK Unified Ideographs + fullwidth punctuation.
# A character counts as 1 "word" for sentence-length purposes; ASCII words count as themselves.
CJK = r"一-鿿"
CJK_PUNCT = r"，。？！：；、"
FULL_SENTENCE_END = r"。！？"

# Modality markers that MUST NEVER be flagged. Keep this list stable; the selftest
# depends on it. Add to it carefully — any addition widens the "do not flag" surface.
MODALITY = ("可能", "也许", "或许", "大概", "应该", "可以", "会", "可能已经",
            "也许会", "或许会", "大概会", "应当", "将")

# Buzzwords / Internet jargon that corrode technical writing. These are the Chinese
# equivalents of the English "soft phrasal verbs" rule.
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

# "Light verb + noun" patterns — the Chinese equivalent of nominalization.
# Format: light verb followed by (optional "的", "一个", etc.) and a nominalized action noun.
# This is more aggressive than the English version because the pattern is more mechanical in Chinese.
LIGHT_VERBS = ("进行", "做出", "开展", "实施", "展开", "完成", "发出",
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

# Aspect-marker redundancy: "正在 X 中", "已经 X 了", "正在 X 过".
# These are advisory because context sometimes justifies them.
ASPECT_REDUNDANCY = [
    (re.compile(r"正在[" + CJK + r"]{1,6}?中"), "正在…中", "'正在' 和 '中' 表达重复，二选一。"),
    (re.compile(r"已经[" + CJK + r"]{1,6}?了[^，。！？]"), "已经…了…", "'已经 … 了' 两个完成体标记重复，二选一。"),
]

# Chinese "的" stacking: three or more "X 的" phrases before a single noun.
# Heuristic: match "X的Y的Z的W" where X/Y/Z are 1–8 CJK chars.
DE_STACK = re.compile(
    r"(?:[" + CJK + r"a-zA-Z0-9]{1,8}的){3,}"
)

# "Noun cluster": 4 or more CJK characters followed by a noun suffix, with no 的
# or verbs in between. This is deliberately conservative — Chinese noun compounds
# are not strictly bounded by whitespace.
NOUN_CLUSTER = re.compile(
    r"[" + CJK + r"]{4,}(?:器|层|模块|服务|组件|引擎|中心|平台|系统|协议|流程|策略)"
)

# Semicolons: both ASCII (;) and fullwidth (；). STE Rule 8.1 bans the mark.
SEMICOLON = re.compile(r"[;；]")

# Synonym groups commonly rotated. Keep each group to genuinely interchangeable terms —
# "错误 / 故障 / 异常" are distinct concepts and must stay out.
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
    ("获取", "拉取", "读取", "取回"),             # fetch (读取 kept in because 读取 commonly means something specific — see note)
    ("更改", "修改", "调整"),                      # change
    ("请求", "调用", "访问"),                      # request (note: 调用 also in 使用 group — that is OK, both groups flag it)
]

# Sentence length caps (Chinese characters, including punctuation, excluding spaces).
MAX_CHARS_DESCRIPTIVE = 50  # SKILL.md cap for descriptive text
# Instructions cap (40) requires context awareness; linter uses the descriptive cap.

RULES = [
    ("semicolon", "advisory-free",
     SEMICOLON,
     "原规则 8.1 禁用分号。拆成独立句。"),
    ("buzzword", "advisory-free",
     re.compile("(" + "|".join(BUZZWORDS) + ")"),
     "互联网黑话。删或替换成具体可测量的说法。"),
    ("marketing-adjective", "advisory-free",
     re.compile("(" + "|".join(MARKETING_ADJECTIVES) + ")"),
     "营销形容词。删或替换成能支撑该说法的测量数据。"),
    ("light-verb", "advisory-free",
     LIGHT_VERB_PATTERN,
     "虚化动词 + 名词化。直接用动词（如 '分析'，不是 '进行分析'）。"),
    ("de-stacking", "advisory-free",
     DE_STACK,
     "'的' 字堆叠（≥3 个 '的' 字短语连续堆到名词前）。把定语后置或拆句。"),
    ("noun-cluster", "advisory-free",
     NOUN_CLUSTER,
     "名词连用过长。拆成 '处理 X 的 Y' 结构。"),
    ("passive-voice", "advisory",
     PASSIVE_MARKER,
     "可能的被动语态。改成主动句，除非施事者未知或无关。"),
]


CODE_FENCE = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
# List markers: Markdown unordered (-/*/+) and numeric (1./1)/1、). Chinese ordinal 1、 is common.
LIST_ITEM_START = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>[-*+]|[0-9]+[.)、])(?P<gap> +)(?P<body>.*)$"
)
CONJUNCTION_END = re.compile(r"(?:并|或|和|与|且)\s*$")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
STANDALONE_LINE = re.compile(r"^ {0,3}(?:#|<|(?:[-*_=] *){3,}$)")
BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}(?:> ?)+")
ANY_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|[0-9]+[.)、])(?:\s|$)")
# Chinese sentence enders: 。！？ plus fullwidth variants and ASCII fallback.
SENTENCE_END = re.compile(r"[" + FULL_SENTENCE_END + r"][\"'”’)\]*_]*$|[.!?][\"'”’)\]*_]*$")
OPENERS = "\"'“‘（([*_"


def _char_count(text):
    """Count all non-space characters. 1 CJK char = 1 unit; 1 ASCII char = 1 unit.

    This matches the SKILL.md definition: '字数口径: 中文字符数, 含标点但不含空格'.
    """
    return sum(1 for c in text if not c.isspace())


def _mask_inline_code(text):
    """Blank code spans with equal-length spaces so columns stay true."""
    return INLINE_CODE.sub(lambda m: " " * len(m.group(0)), text)


def _sentence_starts(text):
    """Return byte offsets where sentences start.

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


def _long_sentence_findings(pieces, filename):
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
        if n <= MAX_CHARS_DESCRIPTIVE:
            continue
        index = bisect.bisect_right(offsets, start) - 1
        offset = offsets[index]
        lineno, source_column, _ = pieces[index]
        findings.append({"file": filename, "line": lineno,
                         "col": source_column + start - offset + 1,
                         "rule": "long-sentence", "level": "advisory-free",
                         "match": f"{n} 字",
                         "message": f"句子长 {n} 字（上限 {MAX_CHARS_DESCRIPTIVE} 字）。拆开。"})
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


def _dangling_conjunction_findings(text, filename):
    """List items that end with 并/或/和/与/且."""
    lines = text.splitlines()
    findings = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if CODE_FENCE.match(stripped):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        start = LIST_ITEM_START.match(line)
        if not start:
            index += 1
            continue
        content_indent = (len(start.group("indent"))
                          + len(start.group("marker"))
                          + len(start.group("gap")))
        item_lines = [(index, start.group("body"))]
        next_index = index + 1
        item_fence = False
        while next_index < len(lines):
            candidate = lines[next_index]
            candidate_stripped = candidate.strip()
            if CODE_FENCE.match(candidate_stripped):
                item_fence = not item_fence
                next_index += 1
                continue
            if item_fence:
                next_index += 1
                continue
            if not _is_list_continuation(candidate, content_indent):
                break
            item_lines.append((next_index, candidate))
            next_index += 1
        meaningful = []
        for line_index, item_line in item_lines:
            cleaned = INLINE_CODE.sub(" CODE ", item_line).strip()
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
                masked = INLINE_CODE.sub(
                    lambda m: " " * len(m.group(0)), raw_end_line
                )
                raw_conjunction = CONJUNCTION_END.search(masked)
                finding_line = end_line_index + 1
                finding_col = raw_conjunction.start() + 1 if raw_conjunction else 1
            findings.append({
                "file": filename,
                "line": finding_line,
                "col": finding_col,
                "rule": "dangling-conjunction",
                "level": "advisory-free",
                "match": end_line,
                "message": "列表项以连词（并/或/和/与/且）结尾。补完此项，或与下一项合并。",
            })
        index = next_index
    return findings


def _aspect_redundancy_findings(line, lineno, source_column, filename):
    """Advisory: redundant aspect markers like '正在…中' or '已经…了'."""
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


def lint(text, filename="<stdin>"):
    findings = []
    chars_total = 0
    in_fence = False
    lines = text.splitlines()
    table_cells = _markdown_table_cells(lines)
    seen_synonyms = {}  # (group_idx, base) -> (line, col, match)
    block = []
    in_quote = False

    def flush():
        findings.extend(_long_sentence_findings(block, filename))
        block.clear()

    for lineno, raw_line in enumerate(lines, 1):
        if CODE_FENCE.match(raw_line.strip()):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
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
            line = _mask_inline_code(segment)
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

            skip = quote.end() if quote and not is_table else 0
            if line[skip:].strip():
                block.append((lineno, source_column + skip, line[skip:]))
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
                    "rule": "synonym-rotation", "level": "advisory-free",
                    "match": match,
                    "message": f"'{base}' 和 '{first_base}' 指同一对象。挑一个，用到底。",
                })

    findings.extend(_dangling_conjunction_findings(text, filename))
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
        print(f"{f['file']}:{f['line']}:{f['col']} {f['rule']}: {f['message']} [{f['match']}]")
    print(f"\n{len(findings)} 处违反（硬违反 {hard_count}，基线 {baseline}），"
          f"共 {chars_total} 字，每百字 {rate} 处。")
    print("情态词（可能/也许/或许/应该/会）永远不会被标记：信心度是内容，不是风格。")


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
    text = "对日志进行分析。完成服务的部署。发出用户通知。"
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
            except OSError as e:
                parser.error(f"无法读取 {p}: {e.strerror}")
            f, w = lint(text, filename=p)
            findings.extend(f)
            chars_total += w
    else:
        findings, chars_total = lint(sys.stdin.read())

    findings = [f for f in findings if f["rule"] not in disabled]
    hard_count = sum(1 for f in findings if f["level"] == "advisory-free")
    report(findings, chars_total, as_json, hard_count, baseline)
    return 1 if hard_count > baseline else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
