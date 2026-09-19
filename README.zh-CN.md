# Hermes Jev 决策副手与模型路由

通用 Hermes 工具插件，同时支持 TypeSafe 官方和 Cloudflare。不是聊天 Provider，不替换主模型。

**v0.1.2 为预发布版。Cloudflare 已完成真实中文基础烟测，返回模型 `jev-1.13.0`；TypeSafe 官方直连及真实业务准确率尚未验证。**

[官方 skill 整理与集成说明](docs/official-skill-notes.zh-CN.md)

## 核心分工

- **代码**：精确规则、算术、权限和硬性风控。
- **Jev**：答案集合明确的分类、真假判断、量表评分。
- **主 Agent / 人**：规划、生成、复杂推理、不确定情况，以及执行授权。

`jev_evaluate` 支持自定义问题和三个快速预设：`task_triage`（任务分类与风险信号）、`next_step`（下一步建议）、`relevance`（资料相关性）。新增 `jev_route`：让 Jev 在 2–32 个候选模型配置中选出更适合当前任务的一个，返回顶层 `selected_model`、`confidence` 和复核状态，完整决策也保留在 `route` 中。

模型路由默认关闭。打开 `model_route_enabled` 后，每轮用户消息会被动调用 Jev：优先用你配置的 `model_routes`，否则自动读取当前 Hermes provider 的模型目录。置信度通过后只改本轮后续请求的 `model` 字段；不换 provider，也不改持久化默认模型。斜杠命令和低置信度不会接管模型。

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

**安装成功不等于桌面会话已收到工具。** 确认实际工具目录中有 `jev_evaluate` 和 `jev_route` 才视为原生入口就绪；新开对话不保证长驻后端刷新插件。工具不可见时，Agent 可直接通过 `hermes jev evaluate --file request.json` 或 `hermes jev route --file route.json` 调用，无需用户自己写命令，也无需重新配置 Token。不要为了加载工具擅自重启正在执行任务的后端。

### 让 Agent 一开始就知道 Jev

Hermes 的 `register_skill()` 注册的是显式加载的 namespaced Skill，**不会自动加入启动提示的 available_skills**。因此本仓库另提供普通发现 Skill：`skills/jev/SKILL.md`。用户可让 Agent 通过 `skill_manage` 将它安装到当前 Profile 的普通技能目录（本地名称 `jev`）；这是显式安装，不在插件加载时偷偷改动用户技能。

普通 Skill 支持这些开场指令：
- “测试 Jev” → 检查配置，再做一次明确告知计费的烟测。
- “Jev 怎么用” → 免费说明，不发模型请求。
- “用 Jev 判断这条任务，只给建议” → 优先工具，缺入口时用 CLI。
- “只检查 Jev 状态，不计费” → 只查本地状态。

`hermes jev guide` 是免费的入门指南。`status` 只验证本地配置，`online_verified: false` 表示该命令未做在线验证，不代表 Token 失效。配套详细指南为 `jev:decision-sidekick`；官方设计指南为 `jev:typesafe-ai`（MIT，固定上游来源）。

```json
{"state":"线上服务白屏，需要先排查原因。","preset":"task_triage"}
```

输出保留答案、概率/置信度、用量和延迟，并给出需要复核的问题。所有结果均为建议，`execution_authorized` 永远为 `false`。

## Cloudflare 的额外前提

`typesafe/jev` 是经 AI Gateway 路由的第三方模型。Token 有效和能读取 Workers AI 模型列表，不等于可以进行统一计费推理。需要启用认证的目标网关和足够的 Unified Billing 余额。

```sh
hermes jev setup --backend cloudflare --account-id 你的账户ID --gateway-id 你的网关ID
```

建议使用独立网关，不要直接改动其他应用共用的默认网关。插件不会创建网关、充值或打开自动充值。HTTP 403、Cloudflare 错误码 2049 应先检查目标网关认证；不要盲目更换 Key。

## 不做什么

不自动批准、不派工、不自动执行命令、不监听全部消息、不每一步都调用、不隐式切换 provider。模型路由只在当前轮请求范围内控制 `model` 字段；默认不启用置信度阈值过滤；如显式配置，须先用目标数据校准，也不能当作正确率保证。输入会发给所选服务商，必须先去除密钥和无关私密信息。

可在插件设置 `model_routes` 中配置模型候选（只放非敏感的模型 ID 和能力描述），例如：

```json
[
  {"id":"fast","model":"your-cheap-model","description":"简单问答、格式化、小改动，成本低、速度快。"},
  {"id":"reasoning","model":"your-reasoning-model","description":"复杂调试、多文件修改和长链路推理。","cost_tier":"high"}
]
```

也可以通过 Hermes 配置命令写入该设置（命令不会发送请求；具体模型 ID 换成你当前 Profile 已配置的值）：

```sh
hermes config set plugins.entries.jev.settings.model_routes '[{"id":"fast","model":"your-cheap-model","description":"简单问答、格式化、小改动，成本低、速度快。"},{"id":"reasoning","model":"your-reasoning-model","description":"复杂调试、多文件修改和长链路推理。","cost_tier":"high"}]'
hermes config set plugins.entries.jev.settings.route_min_confidence 0.8
```

也可以在 `jev_route` 调用时直接传 `candidates`。配置 `route_min_confidence` 后，缺少或低于阈值会返回 `route_needs_review: true`；该阈值不是准确率保证，也不代表执行授权。完整安装、配置、限制和测试见 [README.md](README.md)。生产接入前应以真实中文样本做独立测试；连通性测试不能证明决策可靠。
