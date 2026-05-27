# SourceFuse Demo — AI-Native API Quality Workspace

Postman v12 Native Git demo for SourceFuse. Source of truth for an enterprise-grade,
AI-assisted, source-controlled API quality operating model.

## What's in here

| Path | Purpose |
|---|---|
| `openapi.yaml` | OpenAPI 3.0 contract — the source of truth |
| `postman/collections/` | Source-controlled Postman collections (v12 Native Git format) |
| `postman/environments/` | Dev / QA / Staging / Production environments |
| `postman/globals/` | Workspace globals |
| `.github/workflows/` | CI/CD wiring — quality gate, regression, perf smoke, governance |
| `.spectral.yaml` | Reusable governance ruleset (lint) |
| `scripts/build_workspace.py` | Generator for the Postman workspace tree (idempotent) |

## Collections

- **Customer Onboarding Regression Suite** — multi-folder enterprise regression with chained
  business workflow (auth → customer → KYC → account → payment → notification → audit), plus
  Smoke / Business Validation / Negative Testing / Edge Cases.
- **AI Generated Workflows — Regression Suite / Assertions / Mock Scenarios** — generated and
  maintained by Postbot. Demonstrates AI-driven schema evolution, assertion synthesis, and mock
  scenario generation.
- **Mocks — Core Banking / Payment Processor / Notification Service / Legacy Customer Platform** —
  rich saved examples (success / validation / timeout / partial / rate limit / outage) for
  dependency isolation during shift-left testing.
- **CI Regression Pipeline** — lightweight collection for PR gating.
- **Performance Smoke Validation** — p95 latency, payload size, cache header validation.
- **OpenAPI Synchronization Examples** — demonstrates schema evolution → collection update →
  assertion update without manual maintenance.

## Demo narrative (45–60 min)

1. **Source of truth** — open `openapi.yaml`, show the spec in repo
2. **AI-driven generation** — show `AI Generated Workflows` collections, point at the schema
   evolution example
3. **Enterprise regression** — walk the `Customer Onboarding Regression Suite`, run a folder
4. **Dependency isolation** — switch to the `Mocks — *` collections, show the realistic failure
   scenarios powering shift-left development
5. **Quality in CI/CD** — open `.github/workflows/`, walk the PR quality gate + perf smoke
6. **Governance** — show `.spectral.yaml` + `api-governance.yml`, breaking change detection
7. **Outcomes** — reduced manual scripting, earlier failure detection, reusable governance,
   scalable across every API in the org

## Regenerate the workspace tree

```bash
python3 scripts/build_workspace.py
```

The script is idempotent — it wipes `postman/collections`, `postman/environments`, and
`postman/globals` and rebuilds everything from code. Treat the script as the source of truth
when editing demo content.
