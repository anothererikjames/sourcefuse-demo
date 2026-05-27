# GitHub Actions — SourceFuse Demo

Four workflows wire the Postman collections into CI/CD for the demo.

| Workflow | Trigger | Purpose |
|---|---|---|
| `pr-quality-gate.yml` | PR | Fast (<60s) gate using `CI Regression Pipeline`. Blocks merge on failure. |
| `ci-regression.yml` | PR + push to main + manual | Full `Customer Onboarding Regression Suite` against QA (default). Manual dispatch lets you target Dev/QA/Staging. |
| `performance-smoke.yml` | Schedule (15m) + post-deploy + manual | `Performance Smoke Validation` against Staging/Production. Validates p95 latency, payload size, cache headers. |
| `api-governance.yml` | PR on `openapi.yaml` | Spectral lint + oasdiff breaking-change detection. Reusable across every API in the org. |

## One-time setup

1. Add the **`POSTMAN_API_KEY`** secret in `Settings → Secrets and variables → Actions`.
   Use a key with access to the SourceFuse demo workspace.
2. (Optional) Add **`SLACK_WEBHOOK_URL`** if you want failure notifications to Slack.

## Local execution

You can run any collection locally with the same CLI used in CI:

```bash
postman login --with-api-key "$POSTMAN_API_KEY"

postman collection run "postman/collections/Customer Onboarding Regression Suite" \
  --environment "postman/environments/SourceFuse — QA.environment.yaml"
```

## Demo narrative

- **PR opened** → `pr-quality-gate` runs `CI Regression Pipeline` in ~30s → green check
- **PR merged** → `ci-regression` runs the full suite against QA → JUnit + HTML report uploaded
- **Deploy to staging** → `performance-smoke` runs every 15 min → fails fast if p95 budget breached
- **OAS edited** → `api-governance` runs Spectral + oasdiff → blocks breaking changes at PR time
