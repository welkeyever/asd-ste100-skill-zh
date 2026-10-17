# Linter 边界用例

本文件有刻意的结构违反，用来验证 linter 行为是否符合预期。

## 列表项悬挂连词

- 设定目标并
- 记录结果或

## 代码围栏内不触发

~~~text
- 这一行以 "并" 结尾
~~~

## 分号在代码块里不触发

```python
x = 1; y = 2
```

## 情态词永不触发（SKILL.md 的硬承诺）

本工具可能已经失败。可能的原因有多种。可能的失败场景也许需要人工介入。

验证方法：

```bash
python scripts/ste-lint-zh.py --selftest
python scripts/ste-lint-zh.py examples/linter-edge-cases.md
```

第二条应该报告两个悬挂连词违反，而不报告任何情态词违反。
