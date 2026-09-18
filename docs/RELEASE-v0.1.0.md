# v0.1.0 — Jev decision sidekick (prerelease)

A community Hermes tool plugin supporting TypeSafe official and Cloudflare Jev. It does not replace the main chat model.

## Included

- `jev_evaluate`: mixed Noul/Choice/Score questions and `task_triage`, `next_step`, `relevance` presets.
- `hermes jev setup/status/test/presets/evaluate`: hidden credential entry, explicit provider selection, and profile-scoped settings.
- Official `jev:typesafe-ai` skill, pinned at upstream commit `65a39f393687675ce170e6094757de20370365b9`, with original MIT terms and file hashes.
- Hermes-specific `jev:decision-sidekick` guide, bilingual README and Chinese official-skill integration notes.
- Local control flags cannot be overwritten by provider response fields. No automatic retries, cross-provider failover, hooks or execution permission grants.
- Threshold review is opt-in, not a default universal filter.

## Install

```sh
hermes plugins install ourines/hermes-jev --ref f443b88220af2b65c5853ebd153f1c98bbf350c2 --enable
hermes jev setup --backend typesafe
# Or: hermes jev setup --backend cloudflare
```

Hermes `--ref` accepts only a full 40-character commit SHA, not a tag name. The initial source-archive release draft used a tag; use the corrected installation command on this release page. This is a custom-source plugin, not an entry in the official Hermes catalog. Review the source before enabling it. Setup makes one small billed request before saving credentials. Never send API keys in chat.

## Verified locally

- Hermes 0.21.3, Python 3.11: **31 tests passed**, including actual temporary-profile configuration/secret-scope integration.
- Clean Python 3.12 environment: **30 passed, 1 skipped**; the skipped test requires a Hermes runtime.
- `hermes plugins doctor . --ci` and `hermes plugins validate .` passed.
- Fresh isolated Hermes process: plugin enable, CLI help/status, missing-credential failure and noninteractive setup refusal behaved as expected.
- Original upstream skill/license SHA-256 hashes matched the pinned copies.

Tests use offline fixtures. They do not prove model accuracy or live API access.

## Not yet verified / limitations

- **No successful real TypeSafe or Cloudflare credential call has been recorded for this release.**
- No production workload accuracy, risk-recall, latency or cost benchmark.
- First release supports text instructions/textual rubrics, not the entire upstream structured instruction schema.
- Windows and older Hermes releases have not been tested.
- HTTP proxy environment variables are ignored; timeouts apply per I/O phase, not to an overall deadline.
- State is sent to the chosen provider. Remove credentials and unnecessary personal data first. All decisions remain advisory; preserve human approvals.

## 中文摘要

这是公开预发布版，不是生产可靠性承诺。已包含双后端、交互配置、Agent 工具、三种快捷预设，以及保留来源和 MIT 许可的官方 skill。已通过离线测试和本地 Hermes 集成检查；真实 API 连通性与中文业务评测仍待完成。
