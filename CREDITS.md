# 来源与鸣谢

本项目保留上游来源和版权。以下内容区分直接沿用的设计与延伸阅读，不以 star 数或未经验证的效果作推荐依据。

## 直接上游

[danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) 提供英文技术写作 skill 的结构和思路。本项目沿用 `SKILL.md / references / examples / scripts` 的组织方式、严格与偏意两种模式，以及 linter 的规则表、自检、baseline 和 disable 接口。

中文版重新设计语言规则。本轮调整了语义保真约束、启发式规则级别和 Markdown 处理，并增加回归测试与评估案例。MIT 许可中保留了 Dustin Yuchen Teng 的版权声明。

## 方法与格式

- [ASD-STE100 官方介绍](https://www.asd-ste100.org/about_STE.html)：清晰表达和受控技术写作的来源。本项目不复制其词典，也不代表官方中文标准。
- [Agent Skills 规范](https://agentskills.io/specification)：目录、`SKILL.md` 和元数据格式。
- [Claude Code skills 文档](https://code.claude.com/docs/en/skills)：安装路径和调用方式。

## 中文写作参考

- [sparanoid/chinese-copywriting-guidelines](https://github.com/sparanoid/chinese-copywriting-guidelines)：中英文混排、空格和标点等排版参考。本项目主要处理表达与含义。
- [ruanyf/document-style-guide](https://github.com/ruanyf/document-style-guide)：中文技术文档的组织与表达参考。

## 相关探索

原版仓库列出了以下相关项目，保留链接供读者进一步了解。它们不是运行依赖，本仓库也没有验证组合使用的效果：

- [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing)：英文写作模式检查。
- [andrewroxby/claude-style-patch](https://github.com/andrewroxby/claude-style-patch)：助手写作风格约束。
- [g4lb/asd-ste100-hebrew-skill](https://github.com/g4lb/asd-ste100-hebrew-skill)：其他语言的适配探索。
- [meiluosi/rewrite-fidelity-skill](https://github.com/meiluosi/rewrite-fidelity-skill)：改写前后的含义检查。

如有来源遗漏或归属不准确，请提交 issue 或 PR，并附原始出处。
