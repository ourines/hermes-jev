# v0.1.1 — installer compatibility fix (prerelease)

Supersedes v0.1.0, whose manifest was accepted by the runtime doctor but rejected by the Hermes 0.21.3 installer. The original tag is preserved; do not install v0.1.0.

## Fixed

- Declare manifest schema v1, compatible with the current installer. No runtime features needed schema v2.
- Add a regression test for installer schema compatibility.
- Use a full commit SHA for `hermes plugins install --ref`; tags are not accepted by this installer.

## Included

- Native `jev_evaluate` tool with TypeSafe and Cloudflare backends.
- Hidden interactive API key setup, profile-scoped settings and explicit billed smoke test.
- Task-triage, next-step and relevance presets; custom mixed Noul/Choice/Score questions.
- Original MIT-licensed official TypeSafe skill plus a Hermes runtime guide, Chinese integration notes and bilingual README.
- Provider response fields cannot overwrite local status or advisory-only flags. No hooks, automatic actions or model switching.

## Verification boundaries

Offline tests and Hermes plugin integration are verified separately from actual model calls. **No successful live TypeSafe or Cloudflare API call or workload accuracy benchmark has been recorded.** This remains a prerelease, not a production reliability claim.

The client supports text instructions/textual rubrics only, ignores HTTP proxy environment variables, and uses per-I/O rather than overall deadlines. State goes to the selected provider; minimize it and remove secrets first.

这是安装兼容性修正版，保留 v0.1.0 历史标签，不原地改写。仍未完成真实 API 连通性与中文业务准确率验证。
