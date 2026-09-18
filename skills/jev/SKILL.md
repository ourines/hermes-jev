---
name: jev
description: "Use when Jev is mentioned. Test, classify, score safely."
version: 0.1.0
author: Ourines, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jev, typesafe, classification, decisions]
---

# Jev 决策副手

## When to use
用户提到 Jev、测试 jev、jev 插件、让 Jev 判断，或明确要求用 Jev 做任务分流/下一步建议/资料相关性判断时使用。Jev 是 Hermes 的决策工具插件，不是主聊天模型。不先反问用户 Jev 是什么，也不要求其重讲安装历史；先检查实际可用性。

## 快速处理
- **“测试 Jev”**：用 `terminal` 运行 `hermes jev status`。已配置则告知一次小额真实测试可能计费，运行一次 `hermes jev test`；用户明确只查状态/不计费时只运行 status。未配置才引导 setup。不要重复测试或自动重试。
- **“怎么用 Jev”**：解释三种预设和工具/CLI 两条路径，不调用付费接口。可用 `terminal` 运行 `hermes jev guide`；旧版没有 guide 时用 `hermes jev --help`。
- **“用 Jev 判断……”**：先确定待判断的最小必要内容；优先 `jev_evaluate`。工具不可见就直接使用下述 CLI 路径，不把“缺工具入口”说成“没安装”，不自动重装或改 Token。

## 调用方式
如果工具目录有 `jev_evaluate`，传入：
```json
{"state":"登录页面白屏；目前只允许只读诊断。","preset":"task_triage"}
```
如果目录没有该工具，使用 `write_file` 把请求写到新建的临时 JSON 文件，然后用 `terminal` 运行 `hermes jev evaluate --file <该文件的绝对路径>`。不把请求内容或密钥拼进 shell 命令。用户只要获得结果，无须自己手敲命令。

预设：
- `task_triage`：类别、是否缺必要信息、审批风险；不自动写看板或启动任务。
- `next_step`：state 提供 goal/recent_attempts/observations/permissions；建议继续、有限重试、换方法、询问、升级或停止。
- `relevance`：state 提供 goal 和 item；相关性评分与上下文缺失信号。

`preset` 和 `questions` 二选一。自定义 questions 支持 noul（是的概率）、choice（有限选项）、score（量表），每道题在 instructions 中明确语义。同一状态的独立问题可放一次请求。精确规则、算术用代码，复杂规划由主模型完成。

## 状态和故障
1. `hermes jev status` 只检查本地设置/凭据存在性，不发推理请求。其 `online_verified: false` 不能解读为认证失败，只表示本次状态检查未做在线验证。
2. CLI 工作不等于桌面已收到工具。插件注册的 namespaced Skill 不自动进入 available_skills；本条普通 Skill 提供发现入口。新会话也不保证长驻后端重载插件。只有实际工具目录出现 `jev_evaluate` 才报告原生工具就绪。
3. CLI 命令不存在时，用 `terminal` 运行 `hermes plugins list --plain --no-bundled`，核对当前 Profile；不要读取完整 .env/auth.json，不要盲目重装或重启活跃会话。
4. 403/code 2049：检查所选 AI Gateway 认证；不盲目换 Key/充值。invalid_response：保留静态诊断，不能把接口返回结构不匹配说成 Token 失效。
5. 配置需要用户在交互终端隐藏录入；不从聊天收取 Token。只有用户明确要求配置时才启动 setup，不自动更换主模型或后端。

## 安全与验证
只发送去敏后的必要信息。付费和发送给外部服务的边界应明确；提到 Jev 不等于授权批量评测。结果只作建议，不能批准生产变更、删除、付款、发消息或权限修改。置信度不是正确率保证。

报告实际模型、结果和是否通过，不编造输出。失败时先检查 `ok`，不继续业务执行；降级到主模型必须明确说明没有使用 Jev。基础烟测仅证明连通性及简单判断，不证明真实业务准确率。无需把排查过程全部复述给用户。
