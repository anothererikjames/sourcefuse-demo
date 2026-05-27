#!/usr/bin/env python3
"""
Build the SourceFuse Demo Postman v12 Native Git workspace contents.

Generates collections, environments, globals and saved examples in the
`postman/` directory tree that Postman v12 syncs from a local git repo.

Run from repo root:  python3 scripts/build_workspace.py
"""
from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PM = REPO / "postman"
COLLECTIONS = PM / "collections"
ENVIRONMENTS = PM / "environments"
GLOBALS_DIR = PM / "globals"


# ---------------------------------------------------------------------------
# YAML emitter — small, deterministic, no PyYAML dependency required
# ---------------------------------------------------------------------------

def _yaml_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = (
        s == ""
        or s != s.strip()
        or any(c in s for c in [":", "#", "&", "*", "?", "{", "}", "[", "]", ",", "!", "|", ">", "'", '"', "%", "@", "`"])
        or s.lower() in ("yes", "no", "true", "false", "null", "~")
        or s[:1].isdigit()
        or "\n" in s
    )
    if "\n" in s:
        body = textwrap.indent(s.rstrip("\n"), "  ")
        return "|-\n" + body
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def yaml_dump(obj, indent: int = 0) -> str:
    pad = "  " * indent
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                out.append(f"{pad}{k}:")
                out.append(yaml_dump(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    out.append(f"{pad}{k}: []")
                else:
                    out.append(f"{pad}{k}:")
                    for item in v:
                        if isinstance(item, (dict, list)):
                            # dash + first key inline
                            lines = yaml_dump(item, indent + 1).rstrip("\n").splitlines()
                            if lines:
                                lines[0] = pad + "  - " + lines[0].lstrip()
                                for i in range(1, len(lines)):
                                    lines[i] = "  " + lines[i]
                                out.append("\n".join(lines))
                        else:
                            out.append(f"{pad}  - {_yaml_scalar(item)}")
            else:
                scalar = _yaml_scalar(v)
                if "\n" in scalar:
                    out.append(f"{pad}{k}: {scalar.splitlines()[0]}")
                    for line in scalar.splitlines()[1:]:
                        out.append(f"{pad}{line}")
                else:
                    out.append(f"{pad}{k}: {scalar}")
        return "\n".join(out) + ("\n" if indent == 0 else "")
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lines = yaml_dump(item, indent + 1).rstrip("\n").splitlines()
                if lines:
                    lines[0] = pad + "- " + lines[0].lstrip()
                    for i in range(1, len(lines)):
                        lines[i] = "  " + lines[i]
                    out.append("\n".join(lines))
            else:
                out.append(f"{pad}- {_yaml_scalar(item)}")
        return "\n".join(out) + ("\n" if indent == 0 else "")
    return _yaml_scalar(obj)


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_dump(data))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n")


# ---------------------------------------------------------------------------
# Postman builder helpers
# ---------------------------------------------------------------------------

def collection_def(description: str, variables: dict | None = None,
                   auth: list | None = None) -> dict:
    d: dict = {"$kind": "collection", "description": description}
    if variables:
        d["variables"] = variables
    if auth:
        d["auth"] = auth
    return d


def folder_def(order: int = 1000, description: str | None = None) -> dict:
    d: dict = {"$kind": "collection", "order": order}
    if description:
        d["description"] = description
    return d


def http_request(
    *,
    url: str,
    method: str = "GET",
    description: str | None = None,
    headers: dict | None = None,
    query: list | None = None,
    body_json: dict | None = None,
    pre_script: str | None = None,
    test_script: str | None = None,
    examples_path: str | None = None,
    order: int = 1000,
) -> dict:
    req: dict = {"$kind": "http-request"}
    if description:
        req["description"] = description
    req["url"] = url
    req["method"] = method
    if headers:
        req["headers"] = headers
    if query:
        req["queryParams"] = query
    if body_json is not None:
        req["body"] = {
            "type": "raw",
            "content": json.dumps(body_json, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    scripts = []
    if pre_script:
        scripts.append({"type": "preRequest", "code": pre_script, "language": "text/javascript"})
    if test_script:
        scripts.append({"type": "afterResponse", "code": test_script, "language": "text/javascript"})
    if scripts:
        req["scripts"] = scripts
    if examples_path:
        req["examples"] = examples_path
    req["order"] = order
    return req


def http_example(
    *,
    name: str,
    method: str,
    url: str,
    request_headers: dict | None = None,
    request_body: dict | None = None,
    status_code: int = 200,
    status_text: str = "OK",
    response_headers: dict | None = None,
    response_body: dict | str | None = None,
    order: int = 1000,
) -> dict:
    request: dict = {"url": url, "method": method}
    if request_headers:
        request["headers"] = [{"key": k, "value": v} for k, v in request_headers.items()]
    if request_body is not None:
        request["body"] = {
            "type": "raw",
            "content": json.dumps(request_body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    response: dict = {"statusCode": status_code, "statusText": status_text}
    if response_headers:
        response["headers"] = [{"key": k, "value": v} for k, v in response_headers.items()]
    if response_body is not None:
        if isinstance(response_body, str):
            response["body"] = {"type": "text", "content": response_body}
        else:
            response["body"] = {
                "type": "raw",
                "content": json.dumps(response_body, indent=2),
                "options": {"raw": {"language": "json"}},
            }
    return {"$kind": "http-example", "request": request, "response": response, "order": order}


def write_request(
    *,
    collection_dir: Path,
    folder_segments: list[str],
    request_name: str,
    request: dict,
    examples: list[dict] | None = None,
):
    folder = collection_dir.joinpath(*folder_segments) if folder_segments else collection_dir
    folder.mkdir(parents=True, exist_ok=True)
    # ensure folder definition exists for each intermediate folder (except collection root)
    accum = collection_dir
    for i, seg in enumerate(folder_segments):
        accum = accum / seg
        defp = accum / ".resources" / "definition.yaml"
        if not defp.exists():
            write_yaml(defp, folder_def(order=1000 + i * 100))
    req_file = folder / f"{request_name}.request.yaml"
    if examples:
        ex_dir = folder / ".resources" / f"{request_name}.resources" / "examples"
        ex_dir.mkdir(parents=True, exist_ok=True)
        request["examples"] = f"./.resources/{request_name}.resources/examples"
        for ex in examples:
            ex_name = ex.pop("_name")
            write_yaml(ex_dir / f"{ex_name}.example.yaml", ex)
    write_yaml(req_file, request)


# ---------------------------------------------------------------------------
# Common test/assertion script snippets
# ---------------------------------------------------------------------------

SCHEMA_VALIDATION_HELPER = """
// Shared schema helper — Ajv is available in Postman sandbox
const Ajv = require('ajv');
pm.globals.set('__ajv', 'ready');
""".strip()

P95_LATENCY_BUDGET = 600  # ms

GLOBAL_TESTS = """\
pm.test('Status code is success (2xx)', function () {
    pm.expect(pm.response.code).to.be.within(200, 299);
});

pm.test('Response time below SLO budget (p95)', function () {
    pm.expect(pm.response.responseTime, 'p95 budget 600ms').to.be.below(600);
});

pm.test('Content-Type is application/json', function () {
    if (pm.response.code !== 204) {
        pm.expect(pm.response.headers.get('Content-Type') || '').to.include('application/json');
    }
});

pm.test('Response is valid JSON', function () {
    if (pm.response.code !== 204) pm.response.to.be.json;
});

pm.test('Correlation ID header present', function () {
    pm.expect(pm.response.headers.get('X-Correlation-Id'), 'X-Correlation-Id header').to.be.a('string');
});
"""


def with_business_tests(extra: str) -> str:
    return GLOBAL_TESTS + "\n" + extra.strip() + "\n"


# ---------------------------------------------------------------------------
# Clean target directories so this script is idempotent
# ---------------------------------------------------------------------------

def reset_dirs():
    for d in (COLLECTIONS, ENVIRONMENTS, GLOBALS_DIR):
        if d.exists():
            for p in d.iterdir():
                if p.name == ".gitkeep":
                    continue
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

def build_environments():
    envs = [
        {
            "name": "SourceFuse — Dev",
            "color": "#1d8a4b",
            "values": [
                {"key": "baseUrl", "value": "https://api-dev.sourcefuse-demo.example.com/v1", "enabled": True},
                {"key": "coreBankingUrl", "value": "https://core-banking-dev.sourcefuse-demo.example.com", "enabled": True},
                {"key": "paymentProcessorUrl", "value": "https://payments-dev.sourcefuse-demo.example.com", "enabled": True},
                {"key": "notificationsUrl", "value": "https://notifications-dev.sourcefuse-demo.example.com", "enabled": True},
                {"key": "legacyCustomerUrl", "value": "https://legacy-dev.sourcefuse-demo.example.com", "enabled": True},
                {"key": "authToken", "value": "{{vault:sourcefuse_dev_token}}", "enabled": True, "type": "secret"},
                {"key": "tenantId", "value": "tnt_dev_001", "enabled": True},
                {"key": "kycProvider", "value": "mock", "enabled": True},
                {"key": "p95BudgetMs", "value": "1200", "enabled": True},
                {"key": "featureFlag.aiAssertions", "value": "true", "enabled": True},
            ],
        },
        {
            "name": "SourceFuse — QA",
            "color": "#0079c2",
            "values": [
                {"key": "baseUrl", "value": "https://api-qa.sourcefuse-demo.example.com/v1", "enabled": True},
                {"key": "coreBankingUrl", "value": "https://core-banking-qa.sourcefuse-demo.example.com", "enabled": True},
                {"key": "paymentProcessorUrl", "value": "https://payments-qa.sourcefuse-demo.example.com", "enabled": True},
                {"key": "notificationsUrl", "value": "https://notifications-qa.sourcefuse-demo.example.com", "enabled": True},
                {"key": "legacyCustomerUrl", "value": "https://legacy-qa.sourcefuse-demo.example.com", "enabled": True},
                {"key": "authToken", "value": "{{vault:sourcefuse_qa_token}}", "enabled": True, "type": "secret"},
                {"key": "tenantId", "value": "tnt_qa_001", "enabled": True},
                {"key": "kycProvider", "value": "jumio-sandbox", "enabled": True},
                {"key": "p95BudgetMs", "value": "900", "enabled": True},
                {"key": "featureFlag.aiAssertions", "value": "true", "enabled": True},
            ],
        },
        {
            "name": "SourceFuse — Staging",
            "color": "#cc8a00",
            "values": [
                {"key": "baseUrl", "value": "https://api-staging.sourcefuse-demo.example.com/v1", "enabled": True},
                {"key": "coreBankingUrl", "value": "https://core-banking-staging.sourcefuse-demo.example.com", "enabled": True},
                {"key": "paymentProcessorUrl", "value": "https://payments-staging.sourcefuse-demo.example.com", "enabled": True},
                {"key": "notificationsUrl", "value": "https://notifications-staging.sourcefuse-demo.example.com", "enabled": True},
                {"key": "legacyCustomerUrl", "value": "https://legacy-staging.sourcefuse-demo.example.com", "enabled": True},
                {"key": "authToken", "value": "{{vault:sourcefuse_staging_token}}", "enabled": True, "type": "secret"},
                {"key": "tenantId", "value": "tnt_staging_001", "enabled": True},
                {"key": "kycProvider", "value": "jumio", "enabled": True},
                {"key": "p95BudgetMs", "value": "700", "enabled": True},
                {"key": "featureFlag.aiAssertions", "value": "true", "enabled": True},
            ],
        },
        {
            "name": "SourceFuse — Production",
            "color": "#a92020",
            "values": [
                {"key": "baseUrl", "value": "https://api.sourcefuse-demo.example.com/v1", "enabled": True},
                {"key": "coreBankingUrl", "value": "https://core-banking.sourcefuse-demo.example.com", "enabled": True},
                {"key": "paymentProcessorUrl", "value": "https://payments.sourcefuse-demo.example.com", "enabled": True},
                {"key": "notificationsUrl", "value": "https://notifications.sourcefuse-demo.example.com", "enabled": True},
                {"key": "legacyCustomerUrl", "value": "https://legacy.sourcefuse-demo.example.com", "enabled": True},
                {"key": "authToken", "value": "{{vault:sourcefuse_prod_token}}", "enabled": True, "type": "secret"},
                {"key": "tenantId", "value": "tnt_prod_001", "enabled": True},
                {"key": "kycProvider", "value": "jumio", "enabled": True},
                {"key": "p95BudgetMs", "value": "600", "enabled": True},
                {"key": "featureFlag.aiAssertions", "value": "false", "enabled": True},
            ],
        },
    ]
    for e in envs:
        path = ENVIRONMENTS / f"{e['name']}.environment.yaml"
        write_yaml(path, e)


# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

def build_globals():
    g = {
        "name": "workspace.globals",
        "values": [
            {"key": "demo.workspace", "value": "SourceFuse Demo", "enabled": True},
            {"key": "demo.org", "value": "SourceFuse", "enabled": True},
            {"key": "demo.contact", "value": "demo@sourcefuse.example.com", "enabled": True},
            {"key": "p95BudgetMs", "value": "600", "enabled": True},
            {"key": "schemaVersion", "value": "2026-05-01", "enabled": True},
        ],
    }
    write_yaml(GLOBALS_DIR / "workspace.globals.yaml", g)


# ---------------------------------------------------------------------------
# Customer Onboarding Regression Suite
# ---------------------------------------------------------------------------

def build_customer_onboarding():
    cdir = COLLECTIONS / "Customer Onboarding Regression Suite"
    write_yaml(
        cdir / ".resources" / "definition.yaml",
        collection_def(
            description=textwrap.dedent(
                """\
                # Customer Onboarding Regression Suite

                Enterprise-grade regression suite simulating the complete customer onboarding
                workflow across the SourceFuse banking platform. Designed for CI/CD execution.

                ## Workflow
                1. Authenticate user (service account / OAuth2 client credentials)
                2. Create customer record (PII validated)
                3. Submit KYC verification
                4. Create bank account (savings/checking)
                5. Retrieve account details + funding state
                6. Execute initial funding payment
                7. Send welcome notification
                8. Validate downstream state (audit log, ledger, analytics)
                9. Run negative / failure path scenarios

                ## Folders
                - **Smoke Tests** — health + critical-path requests, <30s run
                - **Regression Tests** — full happy-path business flow
                - **Business Validation** — state-machine, KYC, ledger invariants
                - **Negative Testing** — invalid payload / unauthorized / dependency outage
                - **Edge Cases** — concurrency, idempotency, pagination boundaries, decimal precision

                ## CI/CD
                Designed to be executed via Postman CLI (`postman collection run`) or Newman
                in GitHub Actions. See `.github/workflows/ci-regression.yml`.
                """
            ),
            variables={
                "baseUrl": "{{baseUrl}}",
                "tenantId": "{{tenantId}}",
                "p95BudgetMs": "{{p95BudgetMs}}",
            },
            auth=[
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "type": "bearer",
                    "name": "Service Account",
                    "credentials": {"token": "{{authToken}}"},
                }
            ],
        ),
    )

    # ----- Smoke Tests -----
    smoke_pre = """\
// Smoke pre-request — generate correlation id, capture wall time
pm.variables.set('correlationId', 'cor_' + pm.variables.replaceIn('{{$randomUUID}}'));
pm.variables.set('startedAt', new Date().toISOString());
"""

    write_request(
        collection_dir=cdir,
        folder_segments=["Smoke Tests"],
        request_name="Health check",
        request=http_request(
            url="{{baseUrl}}/health",
            method="GET",
            description="Liveness probe. Must return 200 and a build SHA.",
            headers={"Accept": "application/json", "X-Correlation-Id": "{{correlationId}}"},
            pre_script=smoke_pre,
            test_script=with_business_tests(
                """
pm.test('Service reports healthy', function () {
    const body = pm.response.json();
    pm.expect(body.status).to.eql('ok');
    pm.expect(body).to.have.property('buildSha');
    pm.expect(body.buildSha).to.match(/^[0-9a-f]{7,40}$/);
});
"""
            ),
            order=1000,
        ),
        examples=[
            {
                "_name": "Healthy",
                **http_example(
                    name="Healthy",
                    method="GET",
                    url="{{baseUrl}}/health",
                    status_code=200,
                    response_headers={"Content-Type": "application/json", "X-Correlation-Id": "cor_demo"},
                    response_body={"status": "ok", "buildSha": "a1b2c3d4e5", "uptimeSeconds": 84123},
                )
            }
        ],
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Smoke Tests"],
        request_name="Smoke — list customers (page 1)",
        request=http_request(
            url="{{baseUrl}}/customers?limit=5",
            method="GET",
            description="Reads first page of customers. Confirms read path and tenant scoping.",
            headers={"Accept": "application/json", "X-Tenant-Id": "{{tenantId}}", "X-Correlation-Id": "{{correlationId}}"},
            query=[{"key": "limit", "value": "5"}],
            pre_script=smoke_pre,
            test_script=with_business_tests(
                """
pm.test('Tenant scoping respected', function () {
    const body = pm.response.json();
    pm.expect(body.data, 'data array').to.be.an('array');
    body.data.forEach((c) => pm.expect(c.tenantId).to.eql(pm.variables.get('tenantId')));
});
"""
            ),
            order=1100,
        ),
    )

    # ----- Regression Tests — chained business workflow -----
    auth_test = with_business_tests(
        """
pm.test('Access token returned', function () {
    const body = pm.response.json();
    pm.expect(body.access_token).to.be.a('string').and.match(/^eyJ/);
    pm.expect(body.token_type).to.eql('Bearer');
    pm.expect(body.expires_in).to.be.a('number').and.above(60);
});
const tok = pm.response.json();
pm.collectionVariables.set('serviceToken', tok.access_token);
"""
    )
    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="01 — Authenticate service account",
        request=http_request(
            url="{{baseUrl}}/oauth2/token",
            method="POST",
            description="Service-account OAuth2 client_credentials flow.",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body_json={"grant_type": "client_credentials", "client_id": "demo-client", "client_secret": "{{authToken}}", "scope": "customers.write accounts.write payments.write"},
            pre_script="pm.variables.set('correlationId', 'cor_' + pm.variables.replaceIn('{{$randomUUID}}'));",
            test_script=auth_test,
            order=1000,
        ),
        examples=[
            {
                "_name": "OAuth2 token issued",
                **http_example(
                    name="OAuth2 token issued",
                    method="POST",
                    url="{{baseUrl}}/oauth2/token",
                    status_code=200,
                    response_headers={"Content-Type": "application/json"},
                    response_body={
                        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "scope": "customers.write accounts.write payments.write",
                    },
                )
            }
        ],
    )

    create_customer_pre = """\
// Generate deterministic-but-unique demo customer
const ts = Date.now();
pm.collectionVariables.set('customerEmail', `demo+${ts}@sourcefuse.example.com`);
pm.collectionVariables.set('customerExternalId', `ext_${ts}`);
pm.variables.set('correlationId', 'cor_' + pm.variables.replaceIn('{{$randomUUID}}'));
"""
    create_customer_tests = with_business_tests(
        """
const body = pm.response.json();
pm.collectionVariables.set('customerId', body.id);

pm.test('Customer id is a UUID', function () {
    pm.expect(body.id).to.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
});

pm.test('Required customer fields present', function () {
    ['id','email','firstName','lastName','status','tenantId','createdAt'].forEach((k) => {
        pm.expect(body, `customer.${k}`).to.have.property(k);
    });
});

pm.test('Customer starts in pending_kyc state', function () {
    pm.expect(body.status).to.eql('pending_kyc');
});

pm.test('PII is tokenized in response (no raw SSN)', function () {
    pm.expect(JSON.stringify(body)).to.not.match(/\\b\\d{3}-\\d{2}-\\d{4}\\b/);
});

pm.test('Address validated (nested object)', function () {
    pm.expect(body.address).to.be.an('object');
    pm.expect(body.address.country).to.match(/^[A-Z]{2}$/);
    pm.expect(body.address.postalCode).to.be.a('string').and.have.length.above(2);
});
"""
    )
    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="02 — Create customer",
        request=http_request(
            url="{{baseUrl}}/customers",
            method="POST",
            description="Creates a new prospect customer. Returns id in pending_kyc state.",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
                "Idempotency-Key": "{{$randomUUID}}",
            },
            body_json={
                "externalId": "{{customerExternalId}}",
                "email": "{{customerEmail}}",
                "firstName": "Alex",
                "lastName": "Diaz",
                "dateOfBirth": "1988-04-12",
                "phone": "+1-415-555-0188",
                "address": {
                    "line1": "1 Mission Street",
                    "line2": "Suite 1500",
                    "city": "San Francisco",
                    "state": "CA",
                    "postalCode": "94105",
                    "country": "US",
                },
                "consent": {"tos": True, "privacy": True, "marketing": False},
            },
            pre_script=create_customer_pre,
            test_script=create_customer_tests,
            order=1100,
        ),
        examples=[
            {
                "_name": "Customer created (pending_kyc)",
                **http_example(
                    name="Customer created",
                    method="POST",
                    url="{{baseUrl}}/customers",
                    status_code=201,
                    response_headers={"Content-Type": "application/json", "Location": "/customers/c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22"},
                    response_body={
                        "id": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
                        "tenantId": "tnt_qa_001",
                        "externalId": "ext_1722988800000",
                        "email": "demo+1722988800000@sourcefuse.example.com",
                        "firstName": "Alex",
                        "lastName": "Diaz",
                        "dateOfBirth": "1988-04-12",
                        "phone": "+1-415-555-0188",
                        "status": "pending_kyc",
                        "address": {"line1": "1 Mission Street", "city": "San Francisco", "state": "CA", "postalCode": "94105", "country": "US"},
                        "createdAt": "2026-05-27T17:14:08Z",
                    },
                )
            }
        ],
    )

    kyc_tests = with_business_tests(
        """
const body = pm.response.json();
pm.collectionVariables.set('kycCaseId', body.caseId);

pm.test('KYC case id returned', function () {
    pm.expect(body.caseId).to.match(/^kyc_/);
});

pm.test('KYC state is one of the allowed values', function () {
    pm.expect(body.state).to.be.oneOf(['submitted','manual_review','verified','rejected']);
});

pm.test('Verification factors recorded', function () {
    pm.expect(body.factors).to.be.an('array').that.is.not.empty;
    body.factors.forEach((f) => {
        pm.expect(f.type).to.be.oneOf(['document','liveness','sanctions','pep','address']);
        pm.expect(f.result).to.be.oneOf(['pass','fail','manual']);
    });
});

pm.test('Provider matches environment config', function () {
    pm.expect(body.provider).to.eql(pm.environment.get('kycProvider'));
});
"""
    )
    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="03 — Submit KYC verification",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}/kyc",
            method="POST",
            description="Initiates KYC verification with the configured provider.",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
            },
            body_json={
                "documentType": "drivers_license",
                "documentCountry": "US",
                "documentFrontUrl": "https://uploads.sourcefuse-demo.example.com/demo/dl-front.jpg",
                "documentBackUrl": "https://uploads.sourcefuse-demo.example.com/demo/dl-back.jpg",
                "selfieUrl": "https://uploads.sourcefuse-demo.example.com/demo/selfie.jpg",
            },
            test_script=kyc_tests,
            order=1200,
        ),
        examples=[
            {
                "_name": "KYC verified",
                **http_example(
                    name="KYC verified",
                    method="POST",
                    url="{{baseUrl}}/customers/{{customerId}}/kyc",
                    status_code=201,
                    response_body={
                        "caseId": "kyc_8c1b0e3a",
                        "customerId": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
                        "provider": "jumio-sandbox",
                        "state": "verified",
                        "factors": [
                            {"type": "document", "result": "pass"},
                            {"type": "liveness", "result": "pass"},
                            {"type": "sanctions", "result": "pass"},
                            {"type": "pep", "result": "pass"},
                        ],
                        "verifiedAt": "2026-05-27T17:14:11Z",
                    },
                )
            },
            {
                "_name": "KYC manual review",
                **http_example(
                    name="KYC manual review",
                    method="POST",
                    url="{{baseUrl}}/customers/{{customerId}}/kyc",
                    status_code=202,
                    response_body={
                        "caseId": "kyc_77ab44cc",
                        "customerId": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
                        "provider": "jumio",
                        "state": "manual_review",
                        "factors": [
                            {"type": "document", "result": "pass"},
                            {"type": "liveness", "result": "manual"},
                        ],
                    },
                )
            },
        ],
    )

    account_tests = with_business_tests(
        """
const body = pm.response.json();
pm.collectionVariables.set('accountId', body.id);

pm.test('Account number conforms to format', function () {
    pm.expect(body.accountNumber).to.match(/^\\d{10,12}$/);
});

pm.test('Account type is allowed', function () {
    pm.expect(body.type).to.be.oneOf(['checking','savings','money_market']);
});

pm.test('Status is open', function () {
    pm.expect(body.status).to.eql('open');
});

pm.test('Balance starts at zero with currency', function () {
    pm.expect(body.balance.amount).to.eql('0.00');
    pm.expect(body.balance.currency).to.match(/^[A-Z]{3}$/);
});

pm.test('Linked to authenticated customer', function () {
    pm.expect(body.customerId).to.eql(pm.collectionVariables.get('customerId'));
});
"""
    )
    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="04 — Create bank account",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}/accounts",
            method="POST",
            description="Opens a new account for the customer. Requires verified KYC.",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
            },
            body_json={"type": "checking", "currency": "USD", "nickname": "Primary Checking"},
            test_script=account_tests,
            order=1300,
        ),
        examples=[
            {
                "_name": "Account opened",
                **http_example(
                    name="Account opened",
                    method="POST",
                    url="{{baseUrl}}/customers/{{customerId}}/accounts",
                    status_code=201,
                    response_body={
                        "id": "acc_4f3b1e22",
                        "customerId": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
                        "accountNumber": "100020003001",
                        "routingNumber": "121000358",
                        "type": "checking",
                        "status": "open",
                        "balance": {"amount": "0.00", "currency": "USD"},
                        "openedAt": "2026-05-27T17:14:13Z",
                    },
                )
            }
        ],
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="05 — Get account details",
        request=http_request(
            url="{{baseUrl}}/accounts/{{accountId}}",
            method="GET",
            description="Retrieves canonical account details after creation.",
            headers={
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
            },
            test_script=with_business_tests(
                """
const body = pm.response.json();
pm.test('Account id matches creation response', function () {
    pm.expect(body.id).to.eql(pm.collectionVariables.get('accountId'));
});
pm.test('Funding state is unfunded', function () {
    pm.expect(body.fundingState).to.eql('unfunded');
});
"""
            ),
            order=1400,
        ),
    )

    payment_tests = with_business_tests(
        """
const body = pm.response.json();
pm.collectionVariables.set('paymentId', body.id);

pm.test('Payment id present', function () {
    pm.expect(body.id).to.match(/^pmt_/);
});

pm.test('Amount and currency echoed', function () {
    pm.expect(body.amount).to.eql('250.00');
    pm.expect(body.currency).to.eql('USD');
});

pm.test('Status transitions tracked', function () {
    pm.expect(body.status).to.be.oneOf(['pending','authorized','settled']);
    pm.expect(body.statusHistory).to.be.an('array').that.is.not.empty;
});

pm.test('Ledger entries balance (debit = credit)', function () {
    const debits = body.ledgerEntries.filter((e) => e.direction === 'debit').reduce((s,e) => s + Number(e.amount), 0);
    const credits = body.ledgerEntries.filter((e) => e.direction === 'credit').reduce((s,e) => s + Number(e.amount), 0);
    pm.expect(debits.toFixed(2)).to.eql(credits.toFixed(2));
});
"""
    )
    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="06 — Execute initial funding payment",
        request=http_request(
            url="{{baseUrl}}/payments",
            method="POST",
            description="Pulls funds from an external ACH source and credits the new account.",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
                "Idempotency-Key": "{{$randomUUID}}",
            },
            body_json={
                "type": "ach_pull",
                "amount": "250.00",
                "currency": "USD",
                "destinationAccountId": "{{accountId}}",
                "source": {"type": "external_ach", "routingNumber": "021000021", "accountNumberLast4": "4321"},
                "memo": "Initial funding",
            },
            test_script=payment_tests,
            order=1500,
        ),
        examples=[
            {
                "_name": "Payment settled",
                **http_example(
                    name="Payment settled",
                    method="POST",
                    url="{{baseUrl}}/payments",
                    status_code=201,
                    response_body={
                        "id": "pmt_99a01ff2",
                        "type": "ach_pull",
                        "amount": "250.00",
                        "currency": "USD",
                        "destinationAccountId": "acc_4f3b1e22",
                        "status": "settled",
                        "statusHistory": [
                            {"status": "pending", "at": "2026-05-27T17:14:14Z"},
                            {"status": "authorized", "at": "2026-05-27T17:14:14Z"},
                            {"status": "settled", "at": "2026-05-27T17:14:15Z"},
                        ],
                        "ledgerEntries": [
                            {"account": "external_clearing", "direction": "debit", "amount": "250.00"},
                            {"account": "acc_4f3b1e22", "direction": "credit", "amount": "250.00"},
                        ],
                    },
                )
            }
        ],
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="07 — Send welcome notification",
        request=http_request(
            url="{{notificationsUrl}}/v1/notifications",
            method="POST",
            description="Dispatches the onboarding welcome notification via the notification service.",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {{serviceToken}}",
                "X-Correlation-Id": "{{correlationId}}",
            },
            body_json={
                "channel": "email",
                "template": "onboarding.welcome.v3",
                "to": "{{customerEmail}}",
                "data": {"firstName": "Alex", "accountLast4": "3001"},
            },
            test_script=with_business_tests(
                """
const body = pm.response.json();
pm.test('Notification accepted', function () {
    pm.expect(body.status).to.eql('queued');
    pm.expect(body.notificationId).to.match(/^ntf_/);
});
"""
            ),
            order=1600,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Regression Tests"],
        request_name="08 — Validate downstream audit log",
        request=http_request(
            url="{{baseUrl}}/audit?correlationId={{correlationId}}",
            method="GET",
            description="Confirms the onboarding workflow emitted the expected audit events.",
            headers={
                "Authorization": "Bearer {{serviceToken}}",
                "X-Tenant-Id": "{{tenantId}}",
                "X-Correlation-Id": "{{correlationId}}",
            },
            query=[{"key": "correlationId", "value": "{{correlationId}}"}],
            test_script=with_business_tests(
                """
const body = pm.response.json();
pm.test('All onboarding events emitted', function () {
    const kinds = body.data.map((e) => e.kind);
    ['customer.created','kyc.completed','account.opened','payment.settled','notification.sent']
        .forEach((k) => pm.expect(kinds, k).to.include(k));
});
pm.test('Events share correlation id', function () {
    body.data.forEach((e) => pm.expect(e.correlationId).to.eql(pm.variables.get('correlationId')));
});
"""
            ),
            order=1700,
        ),
    )

    # ----- Business Validation -----
    write_request(
        collection_dir=cdir,
        folder_segments=["Business Validation"],
        request_name="Validate KYC state machine",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}/kyc",
            method="GET",
            description="Asserts the KYC state machine only transitions through allowed states.",
            headers={"Authorization": "Bearer {{serviceToken}}", "X-Tenant-Id": "{{tenantId}}"},
            test_script=with_business_tests(
                """
const allowed = ['submitted','manual_review','verified','rejected'];
const body = pm.response.json();

pm.test('KYC state is allowed', function () {
    pm.expect(allowed).to.include(body.state);
});

pm.test('State transitions are monotonic (no rollback after verified)', function () {
    if (!Array.isArray(body.history)) return;
    let seenVerified = false;
    body.history.forEach((h) => {
        if (h.state === 'verified') seenVerified = true;
        if (seenVerified) {
            pm.expect(['verified','closed']).to.include(h.state);
        }
    });
});
"""
            ),
            order=1000,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Business Validation"],
        request_name="Validate role-based access (analyst read-only)",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}",
            method="DELETE",
            description="Analyst role MUST NOT be able to delete customers. Demonstrates RBAC assertion.",
            headers={
                "Authorization": "Bearer {{analystToken}}",
                "X-Tenant-Id": "{{tenantId}}",
            },
            pre_script="// In real env, analystToken is issued with role=analyst (read-only)\npm.collectionVariables.set('analystToken', 'eyJhbGciOiJSUzI1NiIsInJvbGUiOiJhbmFseXN0In0.demo.sig');",
            test_script="""\
pm.test('Analyst is forbidden from destructive op', function () {
    pm.expect(pm.response.code).to.eql(403);
});
pm.test('Error body has machine-readable code', function () {
    const body = pm.response.json();
    pm.expect(body.error.code).to.eql('rbac.forbidden');
    pm.expect(body.error.requiredRole).to.eql('admin');
});
""",
            order=1100,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Business Validation"],
        request_name="Validate transaction balances (ledger invariant)",
        request=http_request(
            url="{{baseUrl}}/accounts/{{accountId}}/ledger",
            method="GET",
            description="Validates ledger invariant: sum of debits equals sum of credits for the account.",
            headers={"Authorization": "Bearer {{serviceToken}}", "X-Tenant-Id": "{{tenantId}}"},
            test_script=with_business_tests(
                """
const body = pm.response.json();
const debits = body.entries.filter((e) => e.direction === 'debit').reduce((s,e) => s + Number(e.amount), 0);
const credits = body.entries.filter((e) => e.direction === 'credit').reduce((s,e) => s + Number(e.amount), 0);
pm.test('Ledger balances', function () {
    pm.expect(credits.toFixed(2)).to.eql(debits.toFixed(2));
});
pm.test('Closing balance matches running total', function () {
    pm.expect(Number(body.closingBalance)).to.eql(credits - debits + Number(body.openingBalance));
});
"""
            ),
            order=1200,
        ),
    )

    # ----- Negative Testing -----
    write_request(
        collection_dir=cdir,
        folder_segments=["Negative Testing"],
        request_name="Create customer — missing required field",
        request=http_request(
            url="{{baseUrl}}/customers",
            method="POST",
            description="Required field validation: omit email and expect 422.",
            headers={"Authorization": "Bearer {{serviceToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={"firstName": "Alex", "lastName": "Diaz", "dateOfBirth": "1988-04-12"},
            test_script="""\
pm.test('Validation error returned', function () {
    pm.expect(pm.response.code).to.eql(422);
});
pm.test('Error payload identifies missing field', function () {
    const body = pm.response.json();
    pm.expect(body.error.code).to.eql('validation_error');
    pm.expect(body.error.fields).to.be.an('array');
    pm.expect(body.error.fields.map(f => f.field)).to.include('email');
});
""",
            order=1000,
        ),
        examples=[
            {
                "_name": "Validation — missing email",
                **http_example(
                    name="Validation",
                    method="POST",
                    url="{{baseUrl}}/customers",
                    status_code=422,
                    response_body={
                        "error": {
                            "code": "validation_error",
                            "message": "Request failed validation",
                            "fields": [{"field": "email", "rule": "required", "message": "email is required"}],
                        }
                    },
                )
            }
        ],
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Negative Testing"],
        request_name="Create account — unverified KYC",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}/accounts",
            method="POST",
            description="Pre-condition violation: cannot open account without verified KYC.",
            headers={"Authorization": "Bearer {{serviceToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={"type": "checking", "currency": "USD"},
            pre_script="// Force unverified state for negative scenario\npm.collectionVariables.set('customerId', 'c0000000-0000-0000-0000-unverified01');",
            test_script="""\
pm.test('409 Conflict on pre-condition violation', function () {
    pm.expect(pm.response.code).to.eql(409);
});
pm.test('Error code is precondition_failed', function () {
    pm.expect(pm.response.json().error.code).to.eql('precondition_failed');
});
""",
            order=1100,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Negative Testing"],
        request_name="Payment — insufficient funds",
        request=http_request(
            url="{{baseUrl}}/payments",
            method="POST",
            description="Negative scenario: account lacks funds for outbound transfer.",
            headers={"Authorization": "Bearer {{serviceToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={
                "type": "ach_push",
                "amount": "99999.00",
                "currency": "USD",
                "sourceAccountId": "{{accountId}}",
                "destination": {"type": "external_ach", "routingNumber": "021000021", "accountNumberLast4": "1234"},
            },
            test_script="""\
pm.test('402 returned', function () { pm.expect(pm.response.code).to.eql(402); });
pm.test('Error has machine-readable code', function () {
    pm.expect(pm.response.json().error.code).to.eql('insufficient_funds');
});
""",
            order=1200,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Negative Testing"],
        request_name="Unauthorized — missing bearer",
        request=http_request(
            url="{{baseUrl}}/customers",
            method="GET",
            description="No bearer token → 401.",
            headers={"X-Tenant-Id": "{{tenantId}}"},
            test_script="""\
pm.test('401 Unauthorized', function () { pm.expect(pm.response.code).to.eql(401); });
pm.test('WWW-Authenticate header present', function () {
    pm.expect(pm.response.headers.get('WWW-Authenticate') || '').to.include('Bearer');
});
""",
            order=1300,
        ),
    )

    # ----- Edge Cases -----
    write_request(
        collection_dir=cdir,
        folder_segments=["Edge Cases"],
        request_name="Idempotency — replay same key",
        request=http_request(
            url="{{baseUrl}}/payments",
            method="POST",
            description="Replays the same Idempotency-Key. Service must return the same payment without double-charging.",
            headers={
                "Authorization": "Bearer {{serviceToken}}",
                "Content-Type": "application/json",
                "X-Tenant-Id": "{{tenantId}}",
                "Idempotency-Key": "fixed-key-001",
            },
            body_json={"type": "ach_pull", "amount": "10.00", "currency": "USD", "destinationAccountId": "{{accountId}}"},
            test_script="""\
pm.test('Same payment id on replay', function () {
    const body = pm.response.json();
    const prior = pm.collectionVariables.get('idemPaymentId');
    if (prior) {
        pm.expect(body.id).to.eql(prior);
    } else {
        pm.collectionVariables.set('idemPaymentId', body.id);
    }
});
""",
            order=1000,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Edge Cases"],
        request_name="Decimal precision — fractional cents",
        request=http_request(
            url="{{baseUrl}}/payments",
            method="POST",
            description="Service must reject sub-cent precision rather than silently rounding.",
            headers={"Authorization": "Bearer {{serviceToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={"type": "ach_pull", "amount": "10.123", "currency": "USD", "destinationAccountId": "{{accountId}}"},
            test_script="""\
pm.test('Rejects sub-cent precision', function () { pm.expect(pm.response.code).to.eql(422); });
""",
            order=1100,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Edge Cases"],
        request_name="Pagination boundary — limit=0",
        request=http_request(
            url="{{baseUrl}}/customers?limit=0",
            method="GET",
            description="API contract: limit=0 must be rejected (not silently coerced).",
            headers={"Authorization": "Bearer {{serviceToken}}", "X-Tenant-Id": "{{tenantId}}"},
            query=[{"key": "limit", "value": "0"}],
            test_script="""\
pm.test('400 Bad Request', function () { pm.expect(pm.response.code).to.eql(400); });
""",
            order=1200,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["Edge Cases"],
        request_name="Array validation — large bulk import",
        request=http_request(
            url="{{baseUrl}}/customers/bulk",
            method="POST",
            description="Validates per-item errors are returned without failing the whole batch.",
            headers={"Authorization": "Bearer {{serviceToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={
                "items": [
                    {"email": "ok+1@sourcefuse.example.com", "firstName": "Pat", "lastName": "Lee"},
                    {"email": "missing-name@sourcefuse.example.com"},
                    {"firstName": "NoEmail", "lastName": "Person"},
                ]
            },
            test_script="""\
pm.test('Per-item errors returned', function () {
    const body = pm.response.json();
    pm.expect(body.results).to.be.an('array').with.length(3);
    pm.expect(body.results[1].status).to.eql('error');
    pm.expect(body.results[2].status).to.eql('error');
});
""",
            order=1300,
        ),
    )


# ---------------------------------------------------------------------------
# AI Generated Workflows — 3 collections
# ---------------------------------------------------------------------------

def build_ai_workflows():
    ai_root_msg = (
        "# 🤖 AI Generated Workflows\n\n"
        "These collections were **generated and continuously maintained by Postbot / Postman AI**.\n"
        "They demonstrate how AI reduces manual scripting and maintenance effort across:\n\n"
        "- Regression test generation from OpenAPI specs\n"
        "- Assertion generation (business, schema, role-based, nested)\n"
        "- Mock scenario generation\n\n"
        "Every test below was suggested by AI; humans reviewed and accepted.\n"
    )

    # 1) AI Generated Regression Suite
    a1 = COLLECTIONS / "AI Generated Workflows — Regression Suite"
    write_yaml(
        a1 / ".resources" / "definition.yaml",
        collection_def(
            description=ai_root_msg + "\n## AI Generated Regression Suite\n\n"
            "Generated from `openapi.yaml` v1.2 → v1.3. When the schema added `consent.marketing`, "
            "Postbot evolved 14 existing tests and added 3 new ones automatically.\n",
            variables={"baseUrl": "{{baseUrl}}"},
            auth=[
                {
                    "id": "22222222-2222-4222-8222-222222222222",
                    "type": "bearer",
                    "name": "Bearer",
                    "credentials": {"token": "{{authToken}}"},
                }
            ],
        ),
    )

    write_request(
        collection_dir=a1,
        folder_segments=["Generated from schema v1.3"],
        request_name="GET /workspaces — generated test",
        request=http_request(
            url="{{baseUrl}}/workspaces?limit=10",
            method="GET",
            description="**AI-generated regression test** — Postbot synthesized assertions from the OpenAPI response schema for `WorkspacePage`.",
            headers={"Accept": "application/json", "Authorization": "Bearer {{authToken}}"},
            test_script=with_business_tests(
                """
// AI-generated: schema-derived shape assertions
const body = pm.response.json();
pm.test('Top-level shape matches WorkspacePage', function () {
    pm.expect(body).to.have.all.keys('data','nextCursor');
    pm.expect(body.data).to.be.an('array');
});
pm.test('Every workspace conforms to Workspace schema', function () {
    body.data.forEach((w) => {
        pm.expect(w.id).to.match(/^[0-9a-f-]{36}$/);
        pm.expect(w.name).to.be.a('string').with.length.above(0);
        pm.expect(w.slug).to.match(/^[a-z0-9-]+$/);
    });
});
"""
            ),
            order=1000,
        ),
    )

    write_request(
        collection_dir=a1,
        folder_segments=["Generated from schema v1.3"],
        request_name="POST /workspaces — generated test",
        request=http_request(
            url="{{baseUrl}}/workspaces",
            method="POST",
            description="**AI-evolved test** — when `consent.marketing` was added to schema, the assertion below was auto-updated to require it.",
            headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
            body_json={"name": "Acme", "slug": "acme", "description": "Demo workspace"},
            test_script=with_business_tests(
                """
const body = pm.response.json();
// AI-evolved: previously only checked id+name; now also checks createdAt and updatedAt added in v1.3
pm.test('Required fields per schema v1.3', function () {
    ['id','name','slug','createdAt','updatedAt'].forEach((k) => pm.expect(body).to.have.property(k));
});
pm.test('Timestamps are ISO-8601', function () {
    pm.expect(new Date(body.createdAt).toString()).to.not.eql('Invalid Date');
    pm.expect(new Date(body.updatedAt).toString()).to.not.eql('Invalid Date');
});
"""
            ),
            order=1100,
        ),
    )

    # 2) AI Generated Assertions
    a2 = COLLECTIONS / "AI Generated Workflows — Assertions"
    write_yaml(
        a2 / ".resources" / "definition.yaml",
        collection_def(
            description=ai_root_msg + "\n## AI Generated Assertions\n\n"
            "Catalogue of assertion patterns that Postbot can generate on demand. Use this as a "
            "library of examples to copy into your own collections.\n",
            variables={"baseUrl": "{{baseUrl}}"},
        ),
    )

    assertion_examples = [
        ("Business — KYC verification gating", "POST", "/customers/{{customerId}}/accounts",
         with_business_tests("""
pm.test('Cannot create account when KYC unverified (business rule)', function () {
    if (pm.response.code === 409) {
        pm.expect(pm.response.json().error.code).to.eql('precondition_failed');
    }
});
""")),
        ("Schema — strict JSON Schema validation", "GET", "/customers/{{customerId}}",
         with_business_tests("""
const schema = {
    type: 'object',
    required: ['id','email','status','tenantId','address'],
    properties: {
        id: { type: 'string', pattern: '^[0-9a-f-]{36}$' },
        email: { type: 'string', format: 'email' },
        status: { type: 'string', enum: ['pending_kyc','verified','closed'] },
        address: {
            type: 'object',
            required: ['country','postalCode'],
            properties: {
                country: { type: 'string', pattern: '^[A-Z]{2}$' },
                postalCode: { type: 'string' },
            }
        }
    }
};
pm.test('Response matches Customer schema', function () {
    const Ajv = require('ajv'); const ajv = new Ajv({allErrors: true});
    const valid = ajv.validate(schema, pm.response.json());
    pm.expect(valid, JSON.stringify(ajv.errors)).to.be.true;
});
""")),
        ("Nested — deep object validation", "GET", "/payments/{{paymentId}}",
         with_business_tests("""
const p = pm.response.json();
pm.test('Nested ledger entries are well-formed', function () {
    pm.expect(p.ledgerEntries).to.be.an('array').that.is.not.empty;
    p.ledgerEntries.forEach((e) => {
        pm.expect(e).to.include.all.keys('account','direction','amount');
        pm.expect(e.direction).to.be.oneOf(['debit','credit']);
        pm.expect(Number(e.amount)).to.be.a('number').and.above(0);
    });
});
""")),
        ("Required field — exhaustive presence check", "POST", "/customers",
         with_business_tests("""
const required = ['email','firstName','lastName','dateOfBirth','address.country','consent.tos'];
pm.test('All required fields present', function () {
    const b = pm.response.json();
    required.forEach((path) => {
        const v = path.split('.').reduce((o,k) => o && o[k], b);
        pm.expect(v, path).to.not.be.undefined;
    });
});
""")),
        ("Array — uniqueness + ordering", "GET", "/customers?sort=createdAt",
         with_business_tests("""
const body = pm.response.json();
pm.test('IDs are unique', function () {
    const ids = body.data.map((c) => c.id);
    pm.expect(new Set(ids).size).to.eql(ids.length);
});
pm.test('Sorted by createdAt desc', function () {
    const ts = body.data.map((c) => Date.parse(c.createdAt));
    const sorted = [...ts].sort((a,b) => b - a);
    pm.expect(ts).to.eql(sorted);
});
""")),
        ("Negative — invalid token rejected", "GET", "/customers",
         """
pm.test('401 with invalid token', function () { pm.expect(pm.response.code).to.eql(401); });
pm.test('Error code is auth.invalid_token', function () {
    pm.expect(pm.response.json().error.code).to.eql('auth.invalid_token');
});
"""),
        ("Role-based — RBAC matrix", "DELETE", "/customers/{{customerId}}",
         """
const role = pm.environment.get('actorRole') || 'analyst';
pm.test('RBAC enforced for ' + role, function () {
    if (role === 'admin') pm.expect(pm.response.code).to.be.oneOf([200,202,204]);
    else pm.expect(pm.response.code).to.eql(403);
});
"""),
    ]
    for i, (name, method, path, code) in enumerate(assertion_examples):
        write_request(
            collection_dir=a2,
            folder_segments=["Assertion Patterns"],
            request_name=name,
            request=http_request(
                url="{{baseUrl}}" + path,
                method=method,
                description=f"**AI-generated** assertion pattern: {name}.",
                headers={"Authorization": "Bearer {{authToken}}", "Accept": "application/json"},
                test_script=code,
                order=1000 + i * 50,
            ),
        )

    # 3) AI Generated Mock Scenarios
    a3 = COLLECTIONS / "AI Generated Workflows — Mock Scenarios"
    write_yaml(
        a3 / ".resources" / "definition.yaml",
        collection_def(
            description=ai_root_msg + "\n## AI Generated Mock Scenarios\n\n"
            "Postbot generated these mock scenarios from the OpenAPI spec, including failure modes "
            "that aren't represented in the schema but were inferred from operation semantics.\n",
            variables={"baseUrl": "{{baseUrl}}"},
        ),
    )

    write_request(
        collection_dir=a3,
        folder_segments=["Scenarios"],
        request_name="Mock — happy path customer creation",
        request=http_request(
            url="{{baseUrl}}/customers",
            method="POST",
            description="AI-generated mock: returns a freshly created customer.",
            body_json={"email": "demo@sourcefuse.example.com", "firstName": "Pat", "lastName": "Lee"},
            order=1000,
        ),
        examples=[
            {
                "_name": "201 Created",
                **http_example(
                    name="201",
                    method="POST",
                    url="{{baseUrl}}/customers",
                    status_code=201,
                    response_headers={"Content-Type": "application/json", "X-Postman-Mock": "ai-generated"},
                    response_body={"id": "c-ai-001", "email": "demo@sourcefuse.example.com", "status": "pending_kyc"},
                )
            }
        ],
    )
    write_request(
        collection_dir=a3,
        folder_segments=["Scenarios"],
        request_name="Mock — KYC rejected (inferred failure)",
        request=http_request(
            url="{{baseUrl}}/customers/{{customerId}}/kyc",
            method="POST",
            description="AI inferred this failure case from the `state` enum and added a realistic body.",
            body_json={"documentType": "passport", "documentCountry": "US"},
            order=1100,
        ),
        examples=[
            {
                "_name": "201 — KYC rejected",
                **http_example(
                    name="rejected",
                    method="POST",
                    url="{{baseUrl}}/customers/{{customerId}}/kyc",
                    status_code=201,
                    response_body={"caseId": "kyc_ai_reject", "state": "rejected", "reason": "document_expired", "factors": [{"type": "document", "result": "fail"}]},
                )
            }
        ],
    )


# ---------------------------------------------------------------------------
# Mocks (collections with rich saved examples — one per downstream)
# ---------------------------------------------------------------------------

def build_mock_collections():
    def mock_collection(name: str, base_var: str, intro: str, requests: list):
        cdir = COLLECTIONS / name
        write_yaml(
            cdir / ".resources" / "definition.yaml",
            collection_def(
                description=intro,
                variables={"baseUrl": "{{" + base_var + "}}"},
            ),
        )
        for r in requests:
            write_request(collection_dir=cdir, **r)

    # Core Banking
    mock_collection(
        "Mocks — Core Banking",
        "coreBankingUrl",
        "# 🏦 Core Banking Mock\n\n"
        "Simulated core banking system. Use this as a mock server when the real core banking "
        "downstream is unavailable — frontend and QA can build/test in parallel.\n\n"
        "**Scenarios included:** success, validation failure, account closed, timeout, partial data, rate limit.\n",
        [
            {
                "folder_segments": ["Accounts"],
                "request_name": "Get account",
                "request": http_request(
                    url="{{baseUrl}}/v2/accounts/{{accountId}}",
                    method="GET",
                    description="Core banking account read.",
                    headers={"Authorization": "Bearer {{authToken}}"},
                    order=1000,
                ),
                "examples": [
                    {
                        "_name": "200 — Active checking",
                        **http_example(
                            name="200", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=200,
                            response_body={"id": "acc_4f3b1e22", "type": "checking", "status": "open",
                                            "balance": {"amount": "1250.42", "currency": "USD"}, "openedAt": "2025-12-01T08:30:00Z"},
                        )
                    },
                    {
                        "_name": "404 — Not found",
                        **http_example(
                            name="404", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=404, response_body={"error": {"code": "account_not_found", "message": "Account does not exist"}},
                        )
                    },
                    {
                        "_name": "409 — Account closed",
                        **http_example(
                            name="409", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=409, response_body={"error": {"code": "account_closed", "closedAt": "2026-01-15T00:00:00Z"}},
                        )
                    },
                    {
                        "_name": "504 — Upstream timeout",
                        **http_example(
                            name="504", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=504, response_body={"error": {"code": "upstream_timeout", "retryable": True}},
                        )
                    },
                    {
                        "_name": "206 — Partial (balance only)",
                        **http_example(
                            name="206", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=206, response_headers={"X-Partial-Reason": "core-ledger-degraded"},
                            response_body={"id": "acc_4f3b1e22", "balance": {"amount": "1250.42", "currency": "USD"}, "_partial": True},
                        )
                    },
                    {
                        "_name": "429 — Rate limit",
                        **http_example(
                            name="429", method="GET", url="{{baseUrl}}/v2/accounts/{{accountId}}",
                            status_code=429,
                            response_headers={"Retry-After": "12", "X-RateLimit-Remaining": "0"},
                            response_body={"error": {"code": "rate_limited", "retryAfterSeconds": 12}},
                        )
                    },
                ],
            },
            {
                "folder_segments": ["Accounts"],
                "request_name": "Post ledger entry",
                "request": http_request(
                    url="{{baseUrl}}/v2/accounts/{{accountId}}/ledger",
                    method="POST",
                    description="Posts a ledger entry against the account.",
                    headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                    body_json={"direction": "credit", "amount": "100.00", "currency": "USD", "memo": "demo"},
                    order=1100,
                ),
                "examples": [
                    {
                        "_name": "201 — Posted",
                        **http_example(
                            name="201", method="POST", url="{{baseUrl}}/v2/accounts/{{accountId}}/ledger",
                            status_code=201,
                            response_body={"id": "led_001", "balanceAfter": {"amount": "1350.42", "currency": "USD"}},
                        )
                    },
                    {
                        "_name": "422 — Validation failure",
                        **http_example(
                            name="422", method="POST", url="{{baseUrl}}/v2/accounts/{{accountId}}/ledger",
                            status_code=422, response_body={"error": {"code": "validation_error", "fields": [{"field": "amount", "rule": "positive"}]}},
                        )
                    },
                ],
            },
        ],
    )

    # Payment Processor
    mock_collection(
        "Mocks — Payment Processor",
        "paymentProcessorUrl",
        "# 💳 Payment Processor Mock\n\n"
        "Simulated 3rd-party payment processor (Stripe-shaped). Use to isolate the platform from "
        "the live payments provider during development and dependency outages.\n",
        [
            {
                "folder_segments": ["Charges"],
                "request_name": "Create charge",
                "request": http_request(
                    url="{{baseUrl}}/v1/charges",
                    method="POST",
                    description="Authorizes and captures a charge against a customer source.",
                    headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                    body_json={"amount": 25000, "currency": "usd", "source": "src_demo_visa", "description": "Initial funding"},
                    order=1000,
                ),
                "examples": [
                    {
                        "_name": "200 — Captured",
                        **http_example(
                            name="200", method="POST", url="{{baseUrl}}/v1/charges",
                            status_code=200, response_body={"id": "ch_demo_001", "amount": 25000, "currency": "usd", "status": "succeeded"},
                        )
                    },
                    {
                        "_name": "402 — Card declined",
                        **http_example(
                            name="402", method="POST", url="{{baseUrl}}/v1/charges",
                            status_code=402, response_body={"error": {"type": "card_error", "code": "card_declined", "decline_code": "generic_decline"}},
                        )
                    },
                    {
                        "_name": "503 — Provider degraded",
                        **http_example(
                            name="503", method="POST", url="{{baseUrl}}/v1/charges",
                            status_code=503, response_body={"error": {"type": "api_error", "message": "Payment provider is unavailable"}},
                        )
                    },
                    {
                        "_name": "504 — Timeout",
                        **http_example(
                            name="504", method="POST", url="{{baseUrl}}/v1/charges",
                            status_code=504, response_body={"error": {"type": "api_error", "code": "timeout"}},
                        )
                    },
                    {
                        "_name": "429 — Rate limited",
                        **http_example(
                            name="429", method="POST", url="{{baseUrl}}/v1/charges",
                            status_code=429, response_headers={"Retry-After": "5"},
                            response_body={"error": {"type": "rate_limit_error", "message": "Too many requests"}},
                        )
                    },
                ],
            },
        ],
    )

    # Notification Service
    mock_collection(
        "Mocks — Notification Service",
        "notificationsUrl",
        "# 📨 Notification Service Mock\n\n"
        "Simulated multi-channel notification service. Enables shift-left testing of customer comms.\n",
        [
            {
                "folder_segments": ["Send"],
                "request_name": "Send notification",
                "request": http_request(
                    url="{{baseUrl}}/v1/notifications",
                    method="POST",
                    description="Queues a notification for delivery.",
                    headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                    body_json={"channel": "email", "template": "onboarding.welcome.v3", "to": "{{customerEmail}}", "data": {"firstName": "Alex"}},
                    order=1000,
                ),
                "examples": [
                    {
                        "_name": "202 — Queued",
                        **http_example(
                            name="202", method="POST", url="{{baseUrl}}/v1/notifications",
                            status_code=202, response_body={"notificationId": "ntf_001", "status": "queued"},
                        )
                    },
                    {
                        "_name": "400 — Template not found",
                        **http_example(
                            name="400", method="POST", url="{{baseUrl}}/v1/notifications",
                            status_code=400, response_body={"error": {"code": "template_not_found", "template": "onboarding.welcome.v3"}},
                        )
                    },
                    {
                        "_name": "503 — Channel offline",
                        **http_example(
                            name="503", method="POST", url="{{baseUrl}}/v1/notifications",
                            status_code=503, response_body={"error": {"code": "channel_offline", "channel": "sms"}},
                        )
                    },
                    {
                        "_name": "422 — Invalid recipient",
                        **http_example(
                            name="422", method="POST", url="{{baseUrl}}/v1/notifications",
                            status_code=422, response_body={"error": {"code": "validation_error", "fields": [{"field": "to", "rule": "email"}]}},
                        )
                    },
                ],
            },
        ],
    )

    # Legacy Customer Platform
    mock_collection(
        "Mocks — Legacy Customer Platform",
        "legacyCustomerUrl",
        "# 🏛️ Legacy Customer Platform Mock\n\n"
        "Simulated legacy customer platform (SOAP-wrapped behind REST shim). Includes flaky behaviors "
        "(slow responses, intermittent timeouts, partial data) so the new platform can be tested "
        "against realistic legacy degradation.\n",
        [
            {
                "folder_segments": ["Customer"],
                "request_name": "Get legacy customer",
                "request": http_request(
                    url="{{baseUrl}}/customers/{{externalId}}",
                    method="GET",
                    description="Retrieves customer from legacy COBOL-backed platform via REST shim.",
                    headers={"X-Legacy-API-Key": "{{authToken}}"},
                    order=1000,
                ),
                "examples": [
                    {
                        "_name": "200 — Full record",
                        **http_example(
                            name="200", method="GET", url="{{baseUrl}}/customers/{{externalId}}",
                            status_code=200,
                            response_body={"externalId": "ext_1722988800000", "firstName": "Alex", "lastName": "Diaz", "address": {"city": "San Francisco", "state": "CA"}, "legacyAccountNumber": "0001234567"},
                        )
                    },
                    {
                        "_name": "206 — Partial (legacy outage)",
                        **http_example(
                            name="206", method="GET", url="{{baseUrl}}/customers/{{externalId}}",
                            status_code=206, response_headers={"X-Partial-Reason": "mainframe-cics-region-degraded"},
                            response_body={"externalId": "ext_1722988800000", "firstName": "Alex", "_partial": True, "_missing": ["address", "legacyAccountNumber"]},
                        )
                    },
                    {
                        "_name": "504 — Mainframe timeout",
                        **http_example(
                            name="504", method="GET", url="{{baseUrl}}/customers/{{externalId}}",
                            status_code=504, response_body={"error": {"code": "mainframe_timeout", "region": "CICSPROD1"}},
                        )
                    },
                    {
                        "_name": "429 — Throttled by legacy throttle policy",
                        **http_example(
                            name="429", method="GET", url="{{baseUrl}}/customers/{{externalId}}",
                            status_code=429, response_headers={"Retry-After": "60"},
                            response_body={"error": {"code": "legacy_throttled"}},
                        )
                    },
                    {
                        "_name": "200 — Slow response (3500ms)",
                        **http_example(
                            name="200-slow", method="GET", url="{{baseUrl}}/customers/{{externalId}}",
                            status_code=200, response_headers={"X-Response-Time-Ms": "3500"},
                            response_body={"externalId": "ext_1722988800000", "firstName": "Alex", "lastName": "Diaz"},
                        )
                    },
                ],
            },
        ],
    )


# ---------------------------------------------------------------------------
# CI Regression Pipeline + Performance Smoke Validation
# ---------------------------------------------------------------------------

def build_ci_perf():
    ci = COLLECTIONS / "CI Regression Pipeline"
    write_yaml(
        ci / ".resources" / "definition.yaml",
        collection_def(
            description=textwrap.dedent(
                """\
                # 🔁 CI Regression Pipeline

                Lightweight collection executed on every PR via GitHub Actions
                (`.github/workflows/ci-regression.yml`).

                **Purpose:** early API quality visibility inside CI/CD — not a replacement for K6,
                but a shift-left gate that catches breaking contracts and latency regressions before
                they reach perf testing.

                **Quality gates:**
                - 100% of contract assertions pass
                - p95 response time < `{{p95BudgetMs}}` ms
                - Zero schema drift versus the OpenAPI source of truth
                """
            ),
            variables={"baseUrl": "{{baseUrl}}", "p95BudgetMs": "{{p95BudgetMs}}"},
        ),
    )

    write_request(
        collection_dir=ci,
        folder_segments=["Critical path"],
        request_name="Health",
        request=http_request(
            url="{{baseUrl}}/health",
            method="GET",
            description="Liveness gate.",
            test_script=with_business_tests("pm.test('Healthy', () => pm.expect(pm.response.json().status).to.eql('ok'));"),
            order=1000,
        ),
    )
    write_request(
        collection_dir=ci,
        folder_segments=["Critical path"],
        request_name="List customers (smoke)",
        request=http_request(
            url="{{baseUrl}}/customers?limit=5",
            method="GET",
            headers={"Authorization": "Bearer {{authToken}}", "X-Tenant-Id": "{{tenantId}}"},
            test_script=with_business_tests("""\
pm.test('p95 budget honoured (per-request)', function () {
    const budget = Number(pm.environment.get('p95BudgetMs') || 600);
    pm.expect(pm.response.responseTime).to.be.below(budget);
});
"""),
            order=1100,
        ),
    )
    write_request(
        collection_dir=ci,
        folder_segments=["Critical path"],
        request_name="Get OpenAPI spec hash",
        request=http_request(
            url="{{baseUrl}}/openapi.json",
            method="GET",
            description="Fetches live OpenAPI doc and asserts the schema hash matches the spec in the repo. If they drift, CI fails.",
            test_script="""\
pm.test('Spec hash matches expected', function () {
    const body = pm.response.json();
    const expected = pm.environment.get('expectedSpecHash');
    if (expected) pm.expect(body['x-spec-hash']).to.eql(expected);
});
""",
            order=1200,
        ),
    )

    # Performance Smoke
    perf = COLLECTIONS / "Performance Smoke Validation"
    write_yaml(
        perf / ".resources" / "definition.yaml",
        collection_def(
            description=textwrap.dedent(
                """\
                # ⚡ Performance Smoke Validation

                Lightweight latency + payload validation, executed against the deployed environment
                immediately after deploy. **Not a load test, not a K6 replacement** — this is the
                shift-left signal that something is degrading before perf tests run.

                **What it catches:**
                - p95 latency creep
                - Payload size growth
                - Header / cache regression
                - SLO breach on critical endpoints
                """
            ),
            variables={"baseUrl": "{{baseUrl}}", "p95BudgetMs": "{{p95BudgetMs}}"},
        ),
    )

    write_request(
        collection_dir=perf,
        folder_segments=["Latency"],
        request_name="Read latency — list customers",
        request=http_request(
            url="{{baseUrl}}/customers?limit=25",
            method="GET",
            headers={"Authorization": "Bearer {{authToken}}", "X-Tenant-Id": "{{tenantId}}"},
            test_script=with_business_tests("""\
const budget = Number(pm.environment.get('p95BudgetMs') || 600);
pm.test('Per-request latency under budget', function () {
    pm.expect(pm.response.responseTime).to.be.below(budget);
});
pm.test('Payload size < 200 KB', function () {
    pm.expect(pm.response.responseSize).to.be.below(200 * 1024);
});
pm.test('Cache headers present', function () {
    pm.expect(pm.response.headers.get('Cache-Control')).to.be.a('string');
});
"""),
            order=1000,
        ),
    )
    write_request(
        collection_dir=perf,
        folder_segments=["Latency"],
        request_name="Write latency — create customer (will fail when degraded)",
        request=http_request(
            url="{{baseUrl}}/customers",
            method="POST",
            description="Demonstrates a failing run when write latency exceeds budget.",
            headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={"email": "perf+{{$timestamp}}@sourcefuse.example.com", "firstName": "Perf", "lastName": "Smoke", "address": {"country": "US", "postalCode": "94105"}},
            test_script=with_business_tests("""\
const budget = Number(pm.environment.get('p95BudgetMs') || 600);
pm.test('Write under p95 budget', function () {
    pm.expect(pm.response.responseTime).to.be.below(budget);
});
"""),
            order=1100,
        ),
        examples=[
            {
                "_name": "Passing run (480ms)",
                **http_example(
                    name="pass",
                    method="POST",
                    url="{{baseUrl}}/customers",
                    status_code=201,
                    response_headers={"Content-Type": "application/json", "X-Response-Time-Ms": "480"},
                    response_body={"id": "c-perf-pass", "status": "pending_kyc"},
                )
            },
            {
                "_name": "Failing run (980ms — degraded)",
                **http_example(
                    name="fail",
                    method="POST",
                    url="{{baseUrl}}/customers",
                    status_code=201,
                    response_headers={"Content-Type": "application/json", "X-Response-Time-Ms": "980", "X-Postman-Note": "Exceeded p95 budget — gate failed"},
                    response_body={"id": "c-perf-fail", "status": "pending_kyc"},
                )
            },
        ],
    )
    write_request(
        collection_dir=perf,
        folder_segments=["Latency"],
        request_name="Payment latency (downstream sensitive)",
        request=http_request(
            url="{{baseUrl}}/payments/_synthetic",
            method="POST",
            description="Synthetic payment that exercises core banking + processor mocks. Sensitive to downstream latency.",
            headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json", "X-Tenant-Id": "{{tenantId}}"},
            body_json={"type": "synthetic_probe", "amount": "1.00", "currency": "USD"},
            test_script=with_business_tests("""\
const budget = Number(pm.environment.get('p95BudgetMs') || 600);
pm.test('End-to-end payment latency under budget', function () {
    pm.expect(pm.response.responseTime).to.be.below(budget * 2);
});
"""),
            order=1200,
        ),
    )


# ---------------------------------------------------------------------------
# OpenAPI Synchronization Examples — small collection demonstrating drift
# ---------------------------------------------------------------------------

def build_openapi_sync_examples():
    cdir = COLLECTIONS / "OpenAPI Synchronization Examples"
    write_yaml(
        cdir / ".resources" / "definition.yaml",
        collection_def(
            description=textwrap.dedent(
                """\
                # 🔗 OpenAPI Synchronization Examples

                Demonstrates how source-controlled APIs flow into Postman:

                1. **Schema change** — `openapi.yaml` adds `consent.marketing` field
                2. **Collection update** — Postbot regenerates the request body with the new field
                3. **Assertion update** — existing tests evolve to include the new required field
                4. **Reusable governance** — same lint/contract rules apply across every API

                **Outcome:** reduced manual maintenance; standardized API quality at scale.
                """
            ),
            variables={"baseUrl": "{{baseUrl}}"},
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["v1.2 → v1.3 — added consent.marketing"],
        request_name="POST /workspaces (v1.2 — before)",
        request=http_request(
            url="{{baseUrl}}/workspaces",
            method="POST",
            description="**Before:** schema v1.2 — no `consent.marketing`.",
            headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
            body_json={"name": "Acme", "slug": "acme", "description": "v1.2 payload"},
            test_script="""\
pm.test('Created', function () { pm.expect(pm.response.code).to.eql(201); });
""",
            order=1000,
        ),
    )

    write_request(
        collection_dir=cdir,
        folder_segments=["v1.2 → v1.3 — added consent.marketing"],
        request_name="POST /workspaces (v1.3 — after AI sync)",
        request=http_request(
            url="{{baseUrl}}/workspaces",
            method="POST",
            description="**After:** Postbot updated the request body and added an assertion for the new `consent.marketing` field. No manual edits required.",
            headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
            body_json={"name": "Acme", "slug": "acme", "description": "v1.3 payload", "consent": {"tos": True, "privacy": True, "marketing": False}},
            test_script=with_business_tests("""\
const body = pm.response.json();
pm.test('Response echoes consent flags (v1.3)', function () {
    pm.expect(body.consent).to.deep.include({tos: true, privacy: true, marketing: false});
});
pm.test('Required v1.3 fields present', function () {
    ['id','consent','createdAt','updatedAt'].forEach((k) => pm.expect(body).to.have.property(k));
});
"""),
            order=1100,
        ),
    )

    # Governance lint demonstration
    write_request(
        collection_dir=cdir,
        folder_segments=["Reusable Governance"],
        request_name="Lint contract — operationId convention",
        request=http_request(
            url="{{baseUrl}}/workspaces",
            method="GET",
            description="Demonstrates a reusable governance assertion: every list endpoint must support cursor pagination.",
            test_script="""\
pm.test('Cursor pagination contract', function () {
    const body = pm.response.json();
    pm.expect(body).to.have.property('data');
    pm.expect(body).to.have.property('nextCursor');
});
""",
            order=1000,
        ),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    reset_dirs()
    build_environments()
    build_globals()
    build_customer_onboarding()
    build_ai_workflows()
    build_mock_collections()
    build_ci_perf()
    build_openapi_sync_examples()
    print("Built workspace contents under", PM)


if __name__ == "__main__":
    main()
