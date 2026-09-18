# 官方 TypeSafe skill：整理与 Hermes 集成

## 先区分两件事

官方 skill 是供 Agent 阅读的设计与操作知识，不是把 Jev 变成聊天模型的适配器。官方介绍支持以下通用安装路径：

```sh
npx skills add typesafe-ai/skills --skill typesafe-ai
```

安装器中选择目标 Agent。PI 的具体界面选择来自用户分享；本项目没有操作 PI，也不宣称验证过 PI 安装流程。直接使用官方 API 需要账户权限与 `TYPESAFE_API_KEY`。是否需要等待名单，以当前官方控制台状态为准，不把某次申请经历写成永久门槛。

Hermes Jev 插件将 **执行层 + 设计知识层** 一起交付：

| 层 | 内容 | 用途 |
|---|---|---|
| 执行 | `jev_evaluate`、`hermes jev` | Hermes 可直接调用双后端，不需要每次让 Agent 重写 HTTP 代码 |
| 运行指南 | `jev:decision-sidekick` | 何时调用、快速预设、凭据配置、结果解读、安全边界 |
| 官方知识 | `jev:typesafe-ai` | 原版官方 skill，指导原子判断、组合模式、读取实时 docs/cookbooks |

无需再用 npx 为 Hermes 安装一份重复 skill。需要原版指南时显式加载 `jev:typesafe-ai`。

## 从官方 skill 提炼的设计原则

1. **代码拥有流程，模型提供语义判断。** 确定规则、计算、精确查询和执行仍在代码里。
2. **问题 ID 不参与模型判断。** 完整含义放进 `instructions` 和 `criteria`，不要只写在键名。
3. **先给证据，再问问题。** 状态中保留身份、关系、政策和当前事实；必要时使用具名 JSON 字段。
4. **独立问题合并调用。** 同一 state 的多个问题可以并行，但彼此看不到答案。真正依赖前一步的判断才分请求。
5. **选择不等于生成。** 代码先提供候选值或原文片段，Jev 选中后代码复制；缺失候选不会凭空生成。
6. **多标签用多个 Noul。** Choice 只选一个；Score 是按概率加权的量表位置，不是任意数字预测。
7. **置信度不是授权，也不是工作流正确率。** 阈值应结合目标数据与后果，忽略不会用到的分支；多个都可接受的选项也会造成概率分散。
8. **原始判断可复用。** 证据和问题未变时，代码改变权重/展示过滤无需重跑模型。严重违规的“一票否决”应单独组合，不能被加权平均抵消。
9. **类型合法不等于事实正确。** 测试要区分证据缺失、模型错误、代码错误、服务错误。
10. **关注状态时效。** 观察事实与推断分开，应用结果前确认环境没有变化。

## 已落实到插件

- 双后端、一个工具入口；没有把 Jev 伪装成聊天 Provider。
- 同一请求可混合 Noul/Choice/Score，明确无-match/unknown 的候选策略。
- 默认关闭统一阈值过滤，返回原始结果供主 Agent 组合；显式配置的阈值仅为辅助复核。
- 不自动操作看板、执行命令或放行审批；只做按需副手。
- 官方 skill 按提交固定、完整保留 MIT 许可，更新来源可追踪。

## 发布版边界

官方当前允许结构化 instructions/criteria；本插件 v0.1.0 只实现文本指令/文本量表子集。这是客户端范围，不是 Jev 能力限制。

官方 skill 会提示读取实时文档，因此随附快照不代替最新 API/SDK 文档。更新快照时应整体更新目录、许可证、上游提交和哈希，不混用多个版本。

本发布的测试包括离线 HTTP fixtures 和 Hermes 插件/profile 集成。没有成功的真实凭据调用时，不声称已验证线上可用、中文准确率、速度或成本。

## 来源

- [官方 skill](https://github.com/typesafe-ai/skills/blob/65a39f393687675ce170e6094757de20370365b9/skills/typesafe-ai/SKILL.md)
- [官方安装与更新说明](https://docs.typesafe.ai/agent-skill)
- [官方 Quickstart](https://docs.typesafe.ai/introduction/quickstart)
- [Cloudflare Jev](https://developers.cloudflare.com/ai/models/typesafe/jev/)
- 本地精确来源与文件校验值：`UPSTREAM.json`
