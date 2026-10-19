# Linter 边界用例

此文件刻意保留两处列表项不完整的问题。可执行回归见 `tests/test_linter.py`。

## 列表项悬挂连词

- 设定目标并
- 记录结果或

## 代码围栏不触发

````markdown
```python
x = 1; y = 2
```
- 代码中的赋能并
````

## 情态本身不触发

本工具可能已经失败。原因也许是超时。

## 合法领域表达仅供复核

将缓冲区按字节对齐。检查网络链路。

## 验证

```bash
python3 scripts/ste-lint-zh.py --selftest
python3 scripts/ste-lint-zh.py --json examples/linter-edge-cases.md
```

第二条应报告两条硬检查提示，退出码为 `1`。领域表达可能有建议，但不增加硬检查数量。
