# v0.1.2 — authenticated Cloudflare routing and onboarding

This is a community prerelease of **ourines/hermes-jev**, an explicit decision-sidekick plugin. It is not an official TypeSafe, Cloudflare or Nous Research integration. The main Hermes chat model and execution permissions are unchanged.

## Changes since v0.1.1

- Support an explicitly configured authenticated Cloudflare AI Gateway via `--gateway-id`, without creating gateways, changing billing or touching generic Cloudflare credentials.
- Send gateway privacy/cache/attempt controls; explain Cloudflare error code 2049 with bounded, sanitized diagnostics rather than exposing raw error responses.
- Accept the observed Cloudflare `result.result` response envelope with bounded unwrapping and fail-closed checks at each layer.
- Add offline `hermes jev guide`, clearer local-only `status`, and post-setup guidance.
- Bundle an optional ordinary `jev` companion skill for first-mention discovery, with native-tool/CLI fallback and explicit billing boundaries. It must be installed explicitly into the active profile; plugin loading does not write user skills.

## Installation

```sh
hermes plugins install ourines/hermes-jev --ref v0.1.2 --enable
hermes jev guide
hermes jev setup --backend typesafe
# Or use Cloudflare:
# hermes jev setup --backend cloudflare --account-id YOUR_ACCOUNT_ID --gateway-id YOUR_GATEWAY_ID
```

For immutable installation, replace `v0.1.2` with the full commit SHA resolved by the release tag. Setup takes hidden terminal input and makes one tiny potentially billed validation request before saving a credential. `guide`, `status` and `presets` do not call Jev.

A long-running Hermes Desktop backend may need a full restart to discover a newly installed native plugin. Opening a new chat alone is not a guaranteed reload. Do not interrupt active work; the CLI remains a fallback.

## Verification and limits

- 46 tests pass in the local Hermes runtime, including profile-isolation integration.
- Isolated Python 3.11 and 3.12 runs each discover 46 tests: 45 pass and the real-Hermes profile integration test is skipped because Hermes is not installed in those environments.
- Local `hermes plugins validate`, `doctor --ci` and `compat` checks pass; the admission scanner reports `safe`.
- Cloudflare connectivity and a small Chinese Noul/Choice/Score smoke test were verified against `jev-1.13.0`. These are connectivity/basic-semantic checks, not a business-accuracy benchmark.
- TypeSafe direct-account live validation, real-workload accuracy, held-out calibration and comparative latency/cost remain unverified.
- GitHub Actions results are tracked on the exact release commit; local results above do not claim a remote CI result.

## Security and scope

The plugin exposes one tool, `jev_evaluate`, and the `hermes jev` CLI. It registers no hooks or middleware, has no self-updater, does not intercept other tools, and never authorizes execution. Provider responses cannot override local `ok`, advisory or permission fields. Credentials remain in the active Hermes profile's credential lifecycle. Send only the minimum task context required; external-provider inference can be billed.

Official catalog admission is a separate maintainer-reviewed PR. Publishing this release does not imply official catalog acceptance.
