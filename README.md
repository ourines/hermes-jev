# Hermes Jev — decision sidekick

A native **tool plugin**, not a chat-model provider. Jev supplies bounded semantic judgments; the main Hermes agent keeps planning, generation, tool execution and responsibility for approvals.

**v0.1.1 is a prerelease. Real TypeSafe/Cloudflare API access and workload accuracy have not yet been verified.**

[中文使用说明](README.zh-CN.md) · [官方 skill 整理与集成说明](docs/official-skill-notes.zh-CN.md)

## Backends

| Backend | Default model | Credential | Endpoint |
|---|---|---|---|
| TypeSafe official | `jev-latest` | `TYPESAFE_API_KEY` | `https://api.typesafe.ai/v1/systemone` |
| Cloudflare AI | `typesafe/jev` | `CLOUDFLARE_JEV_API_TOKEN` + non-secret Account ID | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run` |

Select one explicitly. No cross-provider fallback, credential reuse, automatic retries or redirected authenticated requests. Model aliases may change upstream; results preserve the actual model ID returned.

## Installation

Requires the Hermes Python environment and its native plugin APIs. Developed against Hermes 0.21.3. Older releases are not verified. Python 3.11+ is recommended.

Public repository install (after the release is published):

```sh
hermes plugins install ourines/hermes-jev --enable
hermes jev setup --backend typesafe
# or: hermes jev setup --backend cloudflare
```

For a reproducible install, add `--ref <full-release-commit-sha>` from the release page. This is a community/custom source, not a Hermes catalog entry. Review source before enabling. Installing official skills separately is unnecessary because a pinned official skill is bundled.

For a local checkout, copy this repository's contents to `<HERMES_HOME>/plugins/jev/` (default `~/.hermes/plugins/jev/`). The directory must directly contain `plugin.yaml` and `__init__.py`. Then:

```sh
hermes plugins doctor /path/to/plugins/jev --ci
hermes plugins enable jev --no-allow-tool-override
hermes jev --help
```

A development symlink from that directory to the checkout is also supported on systems with symlink permissions. No edits to the Hermes core checkout are required. Do not copy `.env`, live configuration or credential files into the plugin repository.

## Interactive setup

```sh
hermes jev setup --backend typesafe
# OR
hermes jev setup --backend cloudflare
```

Setup asks for a Cloudflare Account ID when needed, then uses hidden terminal input for the key. It refuses non-interactive/echo-fallback entry. There is deliberately **no `--api-key` argument**. One tiny live evaluation is made before credentials and connection settings are saved. This can incur usage charges. Failed validation does not save the new credential.

Keys use Hermes's credential save path and reside in the active profile's `.env`/credential lifecycle. Non-secret connection settings use `ctx.set_config()` under `plugins.entries.jev.settings.connection`. Setup verifies the writes by read-back without printing credentials. The main model is untouched. A backend switch is explicit and leaves the previous backend's credential available, but inactive. TypeSafe setup updates that profile's `TYPESAFE_API_KEY`; Cloudflare uses a dedicated slot, never a generic Cloudflare token.

```sh
hermes jev status       # local presence only; not evidence of API access
hermes jev test         # one billed Chinese smoke request, three primitives
hermes jev presets      # show shipped rubrics; offline
hermes jev evaluate --file examples/task-triage.json
```

Use a new Hermes session after enabling so its tool catalog includes `jev_evaluate`; the existing conversation is not hot-mutated. CLI commands work in fresh processes without restarting the desktop. Credentials may require a new session/backend refresh depending on the host's secret-scope snapshot. Do not restart active work just for tool discovery.

## Agent interface

One tool: **`jev_evaluate`**. Exactly one of `preset` and `questions` is required.

```json
{"state":"线上登录白屏，请先排查原因。", "preset":"task_triage"}
```

```json
{
  "state": {"goal":"Repair login", "recent_attempts":["Three identical retries"], "observations":["Same 401"], "permissions":"Read-only diagnosis"},
  "preset":"next_step"
}
```

```json
{"state":{"goal":"Find deployment documentation", "item":"Recipe for soup"}, "preset":"relevance"}
```

For domain-specific decisions, pass named `questions` using Noul/Choice/Score. Consult `examples/custom.json`. Ask independent questions about the same state in one request. The first release supports text instructions and textual criteria (a deliberately smaller subset than the full upstream structured instruction schema).

Load the runtime guide with `skill_view(name="jev:decision-sidekick")`; load the unmodified official design skill with `skill_view(name="jev:typesafe-ai")`. Provenance and MIT notice: `UPSTREAM.json` and `THIRD_PARTY_NOTICES.md`. It teaches when NOT to call Jev as well as the fast path. This is on-demand assistance: no message surveillance, loop hooks, automatic Kanban mutation or implicit model routing.

### Returned information

- `ok`, upstream `model`, `answers`, `usage`, plus backend and measured request latency.
- Raw probability distributions/confidence when supplied by the provider; never invented probabilities.
- `review`: per-question review signals, `advisory_only: true`, `execution_authorized: false`.
- Safe errors rather than request bodies, headers or raw provider errors.

Threshold review is **disabled by default**. Raw judgments remain available for the caller to compose; low confidence is not automatically a failed decision. If explicitly configured, the review threshold is an **uncalibrated heuristic**, not a correctness guarantee. Noul uses the yes-probability bands, not a fabricated confidence. Choice/Score use provider confidence; missing confidence triggers review. Unknown/ask-user/escalate choices trigger review. Risk or missing-context signals may trigger review even when confident. Low uncertainty never substitutes for permission.

To explicitly enable this heuristic using the supported configuration interface (choose a threshold using held-out workload data, not this example):

```sh
hermes config set plugins.entries.jev.settings.review_threshold 0.9
```

## Safety and privacy

- State is sent to the selected external provider. Minimize it and remove credentials/private data before calling.
- No background calls, cross-provider failover, automatic retries, auto-approval or action execution.
- Fixed provider hosts; authenticated redirects are refused. HTTP proxy environment variables are ignored (`trust_env=False`); use an OS-level network route if needed. Requests have per-I/O timeouts (not an overall deadline) and local size limits.
- Credentials/settings are resolved per invocation and profile; no module-global credential cache.
- Prompt wording is not a security boundary. Jev is NOT the sole guardrail for tool safety or permissions.
- API errors return fail-closed advice; the main agent decides whether to ask the user or use other tools. A network error never becomes a synthetic decision.
- No persistent prompt/answer logging or telemetry in the plugin. Hermes's ordinary tool transcript may still retain tool arguments/results.

## Testing

Run from this directory using the Python interpreter in the Hermes environment:

```sh
python -m unittest discover -s tests -v
hermes plugins doctor . --ci
hermes plugins validate .
hermes plugins compat .
```

Tests use clearly labelled local fixtures, not real model outputs. Profile tests exercise actual Hermes config and secret-scope APIs through temporary A → B → A homes. They never write to a user's real profile. Plugin Doctor exercises actual loading/registration while blocking network during registration.

`hermes jev test` is a live connectivity + trivial semantic smoke test, **not an accuracy benchmark**. Before downstream automation, label real Chinese workload data, split prompt-tuning and held-out samples, and compare rules/Jev/main-model on class errors, risk misses, review coverage, p50/p95 latency and total cost including fallbacks. Keep high-risk work under human approval.

## Roadmap boundaries

Useful follow-ups are an offline dataset runner and opt-in application adapters for Kanban/Obsidian. They are not installed or activated by this release. Do not infer production reliability from the synthetic smoke test.

## Reference specifications

- https://docs.typesafe.ai/introduction/quickstart
- https://docs.typesafe.ai/api
- https://docs.typesafe.ai/confidence
- https://developers.cloudflare.com/ai/models/typesafe/jev/
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
