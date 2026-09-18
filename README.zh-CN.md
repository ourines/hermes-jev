# Hermes Jev 决策副手

通用 Hermes 工具插件，同时支持 TypeSafe 官方和 Cloudflare。不是聊天 Provider，不替换主模型。

**v0.1.1 为预发布版；尚未完成真实 API 连通性与业务准确率验证。**

[官方 skill 整理与集成说明](docs/official-skill-notes.zh-CN.md)

## 核心分工

- **代码**：精确规则、算术、权限和硬性风控。
- **Jev**：答案集合明确的分类、真假判断、量表评分。
- **主 Agent / 人**：规划、生成、复杂推理、不确定情况，以及执行授权。

一个 `jev_evaluate` 工具，支持自定义问题和三个快速预设：`task_triage`（任务分类与风险信号）、`next_step`（下一步建议）、`relevance`（资料相关性）。同一状态的一组独立问题放在同一次请求里。

## 使用

公开安装命令（发布后可用）：`hermes plugins install ourines/hermes-jev --enable`。也可以把本地项目放到当前 Profile 的 `plugins/jev/`，再执行：

```sh
hermes plugins enable jev --no-allow-tool-override
hermes jev setup --backend cloudflare
# 官方直连改为：hermes jev setup --backend typesafe
hermes jev status
hermes jev test
```

配置在交互终端输入，Token 隐藏，不放命令参数，也不发聊天。验证成功后保存，主模型不变。配置和测试会发送少量请求，可能计费。

启用后新会话可调用 `jev_evaluate`；当前会话可先用 `hermes jev evaluate --file examples/task-triage.json`。配套运行指南为 `jev:decision-sidekick`，另附原版官方 skill `jev:typesafe-ai`（MIT，固定上游提交与来源）。两者分别解决如何调用、如何设计判断。

```json
{"state":"线上服务白屏，需要先排查原因。","preset":"task_triage"}
```

输出保留答案、概率/置信度、用量和延迟，并给出需要复核的问题。所有结果均为建议，`execution_authorized` 永远为 `false`。

## 不做什么

不自动批准、不派工、不自动执行命令、不监听全部消息、不每一步都调用、不隐式切换后端。默认不启用置信度阈值过滤；如显式配置，须先用目标数据校准，也不能当作正确率保证。输入会发给所选服务商，必须先去除密钥和无关私密信息。

完整安装、配置、限制和测试见 [README.md](README.md)。生产接入前应以真实中文样本做独立测试；连通性测试不能证明决策可靠。
