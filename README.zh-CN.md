# Hermes Jev 决策副手与模型路由

通用 Hermes 工具插件，同时支持 TypeSafe 官方、Cloudflare 和 OpenRouter。不是聊天 Provider，不替换主模型。

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
# OpenRouter 改为：hermes jev setup --backend openrouter
hermes jev status
hermes jev test
```

配置在交互终端输入，Token 隐藏，不放命令参数，也不发聊天。验证成功后保存，主模型不变。配置和测试会发送少量请求，可能计费。

### 复制给 LLM 的配置引导

将下面整段复制到你使用的 LLM 对话中；密钥只在你自己的交互终端输入，不要粘贴到对话里：

```text
请用中文一步一步引导我在当前 Hermes Profile 中安装并初始化 hermes-jev 插件。我会在自己的交互终端执行命令；每次只给我一步，说明预期结果、如何确认成功，以及失败时如何安全排查，等我反馈非敏感结果后再继续。先核对本仓库 README 的实际命令和当前 Hermes 的插件命令帮助，不要猜测命令、配置键或文件路径，也不要擅自改动我的主模型、开启自动路由或重启正在工作的后端。

1. 先确认我已安装 Hermes、当前使用哪个 Profile，以及 Jev 插件是否已安装/启用。询问我选 TypeSafe 官方、Cloudflare 还是 OpenRouter 后端；不要默认复用 Hermes 主模型的 API Key。若未安装，按 README 的公开安装或本地检出流程引导我安装并启用；用插件列表、doctor 及 `hermes jev --help` 确认插件已加载。若公开安装源尚不可用，说明原因并使用 README 中的本地流程，不要编造替代地址。
2. 帮我核对所选后端的前提和独立凭据名称（TypeSafe: TYPESAFE_API_KEY；Cloudflare: CLOUDFLARE_JEV_API_TOKEN，另需 Account ID；OpenRouter: OPENROUTER_JEV_API_TOKEN）。Cloudflare 如使用第三方模型，先检查 AI Gateway 认证与 Unified Billing 前提；不要代我创建网关、充值或改共享网关。确认我接受 setup 的一次可能计费的在线验证后，给出 README 中对应的 `hermes jev setup --backend ...` 命令，让我在交互终端的隐藏输入提示中自行输入密钥。绝不要求我在聊天、命令参数、日志或截图中展示真实 Key，也不要让工具代替我回显、读取或提交密钥；不要手工修改 Hermes 的凭据文件。
3. 让我只反馈去敏的 setup 结果。成功时检查 `ok`、`credential_saved`、`connection_verified` 为 true；再运行 `hermes jev status`，确认 `configured`、`credential_present` 和 backend 与预期一致。解释 status 只检查本地存在性，`online_verified: false` 不表示鉴权失败；setup 验证失败时不得声称凭据已保存。
4. 询问我是否愿意额外支付一次请求做在线烟测；同意后才运行 `hermes jev test`，确认 `ok`、`online_verified` 及 `semantic_checks`，并明确这不是业务准确率测试。用 `hermes jev guide` 免费查看用法。最后检查当前 Agent 的实际工具目录是否有 `jev_evaluate` 和 `jev_route`；CLI 可用不等于桌面/现有会话已加载原生工具。不可见时按 README 的 CLI fallback 引导，不要未经我批准重启后端。逐项告诉我哪些已验证、哪些还没验证。
```

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

## OpenRouter 的说明

```sh
hermes jev setup --backend openrouter
```

OpenRouter 提供的请求/应答契约与官方一致，但走的是 **alpha** 端点，且不存在 `jev-latest` 别名（会返回 `HTTP 400 Model typesafe/jev-latest does not exist`），因此该后端默认固定版本号模型 `typesafe/jev-1.13`，可用 `--model` 覆盖。凭据为独立槽位 `OPENROUTER_JEV_API_TOKEN`：建议单独建一把带额度限制的 Key，不要复用通用 OpenRouter Key。

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

也可以在 `jev_route` 调用时直接传 `candidates`。配置 `route_min_confidence` 后，缺少或低于阈值会返回 `route_needs_review: true`；该阈值不是准确率保证，也不代表执行授权。网关处理一轮消息后，运行 `hermes jev status` 查看 `last_auto_route.applied` 和 `last_auto_route.effective_model`，查看 Jev 中间件的改写结果。普通会话和用量日志打印的是持久化默认模型，不能据此判断请求是否改写；后续中间件仍可能修改请求，该状态也不证明服务商接受了模型。完整安装、配置、限制和测试见 [README.md](README.md)。生产接入前应以真实中文样本做独立测试；连通性测试不能证明决策可靠。
