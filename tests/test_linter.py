"""Behavioral regressions through lint() and the public command-line interface."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ste-lint-zh.py'
SPEC = importlib.util.spec_from_file_location('ste_lint_zh', SCRIPT)
linter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(linter)


def findings(text, rule=None, **kwargs):
    result, _ = linter.lint(text, **kwargs)
    return [f for f in result if rule is None or f['rule'] == rule]


def cli(*args, text=''):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          input=text, capture_output=True, encoding='utf-8')


class LanguageTests(unittest.TestCase):
    def test_domain_terms_do_not_fail(self):
        result = cli('--json', text='将缓冲区按字节对齐。检查网络链路。')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertGreater(data['count'], 0)
        self.assertEqual(data['hard_count'], 0)

    def test_different_operations_are_not_asserted_identical(self):
        result = cli('--json', text='打开文件。启动服务。读取输出。获取令牌。')
        self.assertEqual(result.returncode, 0)
        for item in json.loads(result.stdout)['violations']:
            self.assertEqual(item['level'], 'advisory')

    def test_completion_and_sending_are_not_filler_verbs(self):
        for text in ('已经完成部署。', '完成服务的部署后，再启动测试。', '发出用户通知。'):
            with self.subTest(text=text):
                self.assertEqual(findings(text, 'light-verb'), [])

    def test_modality_alone_does_not_trigger(self):
        for marker in linter.MODALITY:
            with self.subTest(marker=marker):
                self.assertEqual(findings(f'请求{marker}失败。'), [])

    def test_modal_sentence_still_checks_punctuation(self):
        self.assertEqual(len(findings('请求可能失败；请等待。', 'semicolon')), 1)

    def test_natural_aspect_is_not_redundant(self):
        self.assertEqual(findings('已经完成了部署。正在启动中间服务。', 'aspect-marker'), [])
        self.assertEqual(len(findings('任务正在启动中。', 'aspect-marker')), 1)

    def test_light_verb_suggestion_remains(self):
        result = findings('对日志进行分析。', 'light-verb')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['level'], 'advisory')

    def test_character_budget_includes_ascii_and_punctuation(self):
        self.assertEqual(findings('中a。', 'long-sentence', max_chars=3), [])
        self.assertEqual(findings('中a。', 'long-sentence', max_chars=2)[0]['match'], '3 字')

    def test_wrapped_sentence_counts_once(self):
        text = '甲' * 25 + '\n' + '乙' * 25 + '。'
        result = findings(text, 'long-sentence')
        self.assertEqual([(f['line'], f['col'], f['match']) for f in result], [(1, 1, '51 字')])


class MarkdownTests(unittest.TestCase):
    def test_long_outer_fences_hide_inner_fences(self):
        text = '````markdown\n```python\nx = 1; y = 2\n```\n- 赋能并\n````\n正文；继续。'
        result = findings(text)
        self.assertEqual([(f['rule'], f['line'], f['col']) for f in result],
                         [('semicolon', 7, 3)])

    def test_mismatched_fence_does_not_close(self):
        for opener, other in (('```', '~~~'), ('~~~~', '```'), ('````', '```')):
            with self.subTest(opener=opener):
                text = f'{opener}\n{other}\n赋能；\n{opener}\n正文；'
                self.assertEqual([(f['rule'], f['line']) for f in findings(text)], [('semicolon', 5)])

    def test_closing_fence_requires_empty_tail(self):
        self.assertEqual(findings('```\n```python\n赋能；\n```'), [])

    def test_unclosed_fence_hides_remaining_code(self):
        self.assertEqual(findings('```python\n赋能；\n- 记录并'), [])

    def test_quoted_fenced_code(self):
        self.assertEqual(findings('> ```python\n> 赋能；\n> ```'), [])

    def test_multiple_backticks_and_source_columns(self):
        text = '运行 ``echo `赋能;` `` 后；等待。'
        result = findings(text)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['rule'], result[0]['col']), ('semicolon', text.index('；') + 1))

    def test_multiline_inline_code(self):
        self.assertEqual(findings('运行 ``命令\n赋能；``。'), [])

    def test_frontmatter_and_comments_are_not_prose(self):
        text = '---\ndescription: 赋能；\n---\n<!--\n赋能；\n-->\n正文；'
        self.assertEqual([(f['rule'], f['line']) for f in findings(text)], [('semicolon', 7)])

    def test_leading_horizontal_rule_does_not_hide_document(self):
        self.assertEqual(len(findings('---\n正文；继续。', 'semicolon')), 1)

    def test_fence_inside_comment_does_not_hide_later_prose(self):
        text = '<!--\n```\n-->\n正文；继续。'
        self.assertEqual([(f['rule'], f['line']) for f in findings(text)], [('semicolon', 4)])

    def test_comment_marker_inside_inline_code_is_literal(self):
        self.assertEqual(len(findings('使用 `<!--` 标记。正文；继续。', 'semicolon')), 1)

    def test_comment_marker_inside_fence_is_literal(self):
        text = '```html\n<!--\n```\n正文；继续。'
        self.assertEqual([(f['rule'], f['line']) for f in findings(text)], [('semicolon', 4)])

    def test_code_ending_item_is_not_dangling(self):
        self.assertEqual(findings('- 检查并 `run`', 'dangling-conjunction'), [])
        self.assertEqual(findings('- `并`', 'dangling-conjunction'), [])

    def test_real_dangling_items_and_continuations(self):
        text = '- 检查并\n  记录结果\n- 等待或\n- 关闭窗口'
        result = findings(text, 'dangling-conjunction')
        self.assertEqual([(f['line'], f['col']) for f in result], [(3, 1)])

    def test_dangling_match_preserves_code_spelling(self):
        result = findings('- 检查 `run` 并', 'dangling-conjunction')
        self.assertEqual(result[0]['match'], '检查 `run` 并')

    def test_table_cells_have_independent_budgets(self):
        text = '| 标签 | 内容 |\n| --- | --- |\n| ' + '甲' * 30 + ' | ' + '乙' * 30 + ' |'
        self.assertEqual(findings(text, 'long-sentence'), [])

    def test_inline_pipe_does_not_split_table(self):
        text = '| 标签 | 内容 |\n| --- | --- |\n| `a|b` | 正文； |'
        result = findings(text, 'semicolon')
        self.assertEqual((result[0]['line'], result[0]['col']),
                         (3, text.splitlines()[2].index('；') + 1))

    def test_markdown_prefixes_do_not_use_sentence_budget(self):
        for prefix in ('# ', '- ', '1. ', '> ', '> - '):
            with self.subTest(prefix=prefix):
                self.assertEqual(findings(prefix + '甲' * 49 + '。', 'long-sentence'), [])

    def test_unicode_column_after_prefix(self):
        text = '> - 甲😀；乙。'
        result = findings(text, 'semicolon')
        self.assertEqual(result[0]['col'], text.index('；') + 1)


class CommandTests(unittest.TestCase):
    def test_json_contract(self):
        result = cli('--json', text='任务；继续。')
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual((data['count'], data['hard_count'], data['baseline'], data['chars']), (1, 1, 0, 6))
        self.assertEqual(data['per_100_chars'], 16.7)
        self.assertEqual(data['violations'][0]['file'], '<stdin>')
        self.assertEqual(data['violations'][0]['col'], 3)

    def test_baseline_is_inclusive(self):
        self.assertEqual(cli('--baseline', 1, text='甲；乙。').returncode, 0)
        self.assertEqual(cli('--baseline', 0, text='甲；乙。').returncode, 1)

    def test_disable_removes_findings_not_characters(self):
        result = cli('--json', '--disable', 'semicolon', text='甲；乙。')
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual((data['count'], data['chars']), (0, 4))

    def test_configurable_budget(self):
        self.assertEqual(cli('--max-chars', 40, text='甲' * 40 + '。').returncode, 1)
        self.assertEqual(cli(text='甲' * 40 + '。').returncode, 0)

    def test_invalid_arguments(self):
        for args in (('--max-chars', '0'), ('--max-chars', '-1'), ('--max-chars', 'x'),
                     ('--baseline', '-1'), ('--basline', '1'), ('--disable', 'not-a-rule')):
            with self.subTest(args=args):
                result = cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)

    def test_unreadable_and_non_utf8_files(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'bad.md'
            bad.write_bytes(b'\xff\xfe')
            for path in (bad, bad.with_name('missing.md')):
                with self.subTest(path=path):
                    result = cli('--json', path)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, '')
                    self.assertNotIn('Traceback', result.stderr)

    def test_non_utf8_stdin(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--json'],
                                input=b'\xff', capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn(b'Traceback', result.stderr)

    def test_multifile_total_and_intermixed_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('a.md', 'b.md')]
            for path in paths:
                path.write_text('甲；乙。', encoding='utf-8')
            result = cli(paths[0], '--json', '--baseline', 1, paths[1])
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertEqual((data['chars'], data['hard_count']), (8, 2))
            self.assertEqual([f['file'] for f in data['violations']], list(map(str, paths)))


if __name__ == '__main__':
    unittest.main()
