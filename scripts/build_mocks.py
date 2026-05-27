#!/usr/bin/env python3
"""
Create live Postman mock servers for the SourceFuse demo.

For each downstream + the platform itself we:
  1. POST a Postman v2.1 collection (with rich saved examples) to the workspace
  2. POST a mock server bound to that collection
  3. Capture the mock URL

At the end we write `postman/environments/SourceFuse — Mock.environment.yaml`
with every *Url variable repointed at the mock URLs so the existing
regression suite can run end-to-end against the mocks.

Requires:
  POSTMAN_API_KEY environment variable
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import time
from pathlib import Path
from urllib import request, error

REPO = Path(__file__).resolve().parents[1]
ENV_DIR = REPO / "postman" / "environments"
WORKSPACE_ID = "f6ab418b-b4d3-47a3-905c-71601d964f6d"
API = "https://api.getpostman.com"
KEY = os.environ.get("POSTMAN_API_KEY")
if not KEY:
    print("ERROR: POSTMAN_API_KEY env var required", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, method=method, headers={
        "X-API-Key": KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {method} {url}\n{msg}")


def find_existing(name: str) -> str | None:
    """Return existing collection UID for a given name in our workspace."""
    data = _req("GET", f"/collections?workspace={WORKSPACE_ID}")
    for c in data.get("collections", []):
        if c.get("name") == name:
            return c.get("uid")
    return None


def delete_collection(uid: str) -> None:
    _req("DELETE", f"/collections/{uid}")


def create_collection(collection: dict) -> tuple[str, str]:
    """POST a v2.1 collection, return (uid, id)."""
    body = {"collection": collection}
    res = _req("POST", f"/collections?workspace={WORKSPACE_ID}", body)
    coll = res.get("collection", {})
    return coll["uid"], coll["id"]


def create_mock(collection_uid: str, name: str) -> dict:
    body = {
        "mock": {
            "name": name,
            "collection": collection_uid,
            "private": False,
        }
    }
    res = _req("POST", f"/mocks?workspace={WORKSPACE_ID}", body)
    return res.get("mock", {})


def list_mocks() -> list:
    return _req("GET", f"/mocks?workspace={WORKSPACE_ID}").get("mocks", [])


# ---------------------------------------------------------------------------
# Postman v2.1 collection builder
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def header_list(headers: dict | None) -> list:
    if not headers:
        return []
    return [{"key": k, "value": v} for k, v in headers.items()]


def url_obj(raw_url: str) -> dict:
    # raw_url: https://host/path/segments?a=b
    if "://" in raw_url:
        proto, rest = raw_url.split("://", 1)
        host_path, _, query = rest.partition("?")
        host, _, path = host_path.partition("/")
        url = {
            "raw": raw_url,
            "protocol": proto,
            "host": host.split("."),
            "path": [p for p in path.split("/") if p],
        }
    else:
        host_path, _, query = raw_url.partition("?")
        url = {
            "raw": raw_url,
            "host": ["{{baseUrl}}"],
            "path": [p for p in host_path.split("/") if p and p != "{{baseUrl}}"],
        }
    if query:
        url["query"] = [
            {"key": kv.split("=", 1)[0], "value": kv.split("=", 1)[1] if "=" in kv else ""}
            for kv in query.split("&")
        ]
    return url


def request_obj(method: str, raw_url: str, *, headers: dict | None = None,
                body: dict | None = None) -> dict:
    r = {
        "method": method,
        "header": header_list(headers),
        "url": url_obj(raw_url),
    }
    if body is not None:
        r["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    return r


def example(name: str, *, method: str, raw_url: str,
            status_code: int, status_text: str = "OK",
            response_headers: dict | None = None,
            response_body: dict | str | None = None,
            request_headers: dict | None = None,
            request_body: dict | None = None) -> dict:
    body_text = ""
    if isinstance(response_body, dict):
        body_text = json.dumps(response_body, indent=2)
    elif isinstance(response_body, str):
        body_text = response_body
    return {
        "id": _uuid(),
        "name": name,
        "originalRequest": request_obj(method, raw_url,
                                       headers=request_headers,
                                       body=request_body),
        "status": status_text,
        "code": status_code,
        "_postman_previewlanguage": "json",
        "header": header_list({"Content-Type": "application/json", **(response_headers or {})}),
        "cookie": [],
        "body": body_text,
    }


def request_item(name: str, *, method: str, raw_url: str,
                 headers: dict | None = None,
                 body: dict | None = None,
                 examples: list | None = None) -> dict:
    return {
        "id": _uuid(),
        "name": name,
        "request": request_obj(method, raw_url, headers=headers, body=body),
        "response": examples or [],
    }


def folder(name: str, items: list) -> dict:
    return {"id": _uuid(), "name": name, "item": items}


def collection(name: str, description: str, items: list) -> dict:
    return {
        "info": {
            "_postman_id": _uuid(),
            "name": name,
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }


# ---------------------------------------------------------------------------
# Define the 5 collections to push to cloud as mockable
# ---------------------------------------------------------------------------

def build_platform_collection() -> dict:
    base = "{{baseUrl}}"

    # OAuth2 token
    oauth_examples = [
        example(
            "OAuth2 token issued",
            method="POST", raw_url=f"{base}/oauth2/token",
            status_code=200,
            request_body={"grant_type": "client_credentials", "client_id": "demo-client", "client_secret": "***", "scope": "customers.write accounts.write payments.write"},
            response_body={
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "customers.write accounts.write payments.write",
            },
        )
    ]

    # /health
    health_examples = [example(
        "Healthy", method="GET", raw_url=f"{base}/health", status_code=200,
        response_headers={"X-Correlation-Id": "cor_demo"},
        response_body={"status": "ok", "buildSha": "a1b2c3d4e5", "uptimeSeconds": 84123},
    )]

    # /customers list
    list_cust_examples = [example(
        "Page of customers", method="GET", raw_url=f"{base}/customers?limit=5", status_code=200,
        response_headers={"X-Correlation-Id": "cor_demo", "Cache-Control": "max-age=30"},
        response_body={
            "data": [
                {"id": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22", "tenantId": "tnt_qa_001", "email": "alex@sourcefuse.example.com", "firstName": "Alex", "lastName": "Diaz", "status": "verified", "address": {"country": "US", "postalCode": "94105"}, "createdAt": "2026-05-20T17:14:08Z"},
                {"id": "a8e1d9a0-3a44-4f70-9a8a-1c2b3d4e5f6a", "tenantId": "tnt_qa_001", "email": "jamie@sourcefuse.example.com", "firstName": "Jamie", "lastName": "Park", "status": "pending_kyc", "address": {"country": "US", "postalCode": "10001"}, "createdAt": "2026-05-21T09:02:18Z"},
            ],
            "nextCursor": None,
        },
    )]

    # /customers create
    create_cust_examples = [
        example(
            "Customer created", method="POST", raw_url=f"{base}/customers", status_code=201,
            response_headers={"Location": "/customers/c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22", "X-Correlation-Id": "cor_demo"},
            request_body={"email": "demo@sourcefuse.example.com", "firstName": "Alex", "lastName": "Diaz"},
            response_body={
                "id": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
                "tenantId": "tnt_qa_001",
                "externalId": "ext_demo",
                "email": "demo@sourcefuse.example.com",
                "firstName": "Alex",
                "lastName": "Diaz",
                "dateOfBirth": "1988-04-12",
                "phone": "+1-415-555-0188",
                "status": "pending_kyc",
                "address": {"line1": "1 Mission Street", "city": "San Francisco", "state": "CA", "postalCode": "94105", "country": "US"},
                "createdAt": "2026-05-27T17:14:08Z",
            },
        ),
        example(
            "Validation — missing email", method="POST", raw_url=f"{base}/customers", status_code=422,
            response_body={"error": {"code": "validation_error", "message": "Request failed validation", "fields": [{"field": "email", "rule": "required"}]}},
        ),
    ]

    # /customers/:id
    get_cust_examples = [example(
        "Customer record", method="GET", raw_url=f"{base}/customers/:customerId", status_code=200,
        response_body={
            "id": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
            "tenantId": "tnt_qa_001",
            "email": "demo@sourcefuse.example.com",
            "firstName": "Alex",
            "lastName": "Diaz",
            "status": "verified",
            "address": {"country": "US", "postalCode": "94105"},
            "createdAt": "2026-05-27T17:14:08Z",
        },
    )]

    delete_cust_examples = [example(
        "RBAC forbidden", method="DELETE", raw_url=f"{base}/customers/:customerId", status_code=403,
        response_body={"error": {"code": "rbac.forbidden", "requiredRole": "admin", "actorRole": "analyst"}},
    )]

    # /customers/:id/kyc
    kyc_post_examples = [example(
        "KYC verified", method="POST", raw_url=f"{base}/customers/:customerId/kyc", status_code=201,
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
    )]

    kyc_get_examples = [example(
        "KYC current state", method="GET", raw_url=f"{base}/customers/:customerId/kyc", status_code=200,
        response_body={
            "caseId": "kyc_8c1b0e3a",
            "customerId": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
            "state": "verified",
            "history": [
                {"state": "submitted", "at": "2026-05-27T17:14:09Z"},
                {"state": "verified", "at": "2026-05-27T17:14:11Z"},
            ],
        },
    )]

    # /customers/:id/accounts (open account)
    open_acc_examples = [
        example(
            "Account opened", method="POST", raw_url=f"{base}/customers/:customerId/accounts", status_code=201,
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
    ]

    # /accounts/:id
    get_acc_examples = [example(
        "Account details", method="GET", raw_url=f"{base}/accounts/:accountId", status_code=200,
        response_body={
            "id": "acc_4f3b1e22",
            "customerId": "c2c8c0f6-7d6d-4ad9-9c1a-9b6a3a3f1b22",
            "accountNumber": "100020003001",
            "type": "checking",
            "status": "open",
            "balance": {"amount": "0.00", "currency": "USD"},
            "fundingState": "unfunded",
            "openedAt": "2026-05-27T17:14:13Z",
        },
    )]

    # /accounts/:id/ledger
    ledger_examples = [example(
        "Ledger entries", method="GET", raw_url=f"{base}/accounts/:accountId/ledger", status_code=200,
        response_body={
            "accountId": "acc_4f3b1e22",
            "openingBalance": "0.00",
            "closingBalance": "250.00",
            "entries": [
                {"direction": "credit", "amount": "250.00", "memo": "Initial funding", "at": "2026-05-27T17:14:15Z"},
                {"direction": "debit", "amount": "250.00", "memo": "External clearing", "at": "2026-05-27T17:14:15Z"},
            ],
        },
    )]

    # /payments
    pay_examples = [
        example(
            "Payment settled", method="POST", raw_url=f"{base}/payments", status_code=201,
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
        ),
        example(
            "Insufficient funds", method="POST", raw_url=f"{base}/payments", status_code=402,
            response_body={"error": {"code": "insufficient_funds", "message": "Source account has insufficient balance"}},
        ),
        example(
            "Validation — fractional cents", method="POST", raw_url=f"{base}/payments", status_code=422,
            response_body={"error": {"code": "validation_error", "fields": [{"field": "amount", "rule": "two_decimal_places"}]}},
        ),
    ]

    # /payments/_synthetic
    synth_examples = [example(
        "Synthetic probe", method="POST", raw_url=f"{base}/payments/_synthetic", status_code=201,
        response_body={"id": "pmt_synthetic", "status": "settled", "probeLatencyMs": 412},
    )]

    # /audit
    audit_examples = [example(
        "Audit events", method="GET", raw_url=f"{base}/audit?correlationId=cor_demo", status_code=200,
        response_body={
            "data": [
                {"kind": "customer.created", "correlationId": "cor_demo", "at": "2026-05-27T17:14:08Z"},
                {"kind": "kyc.completed", "correlationId": "cor_demo", "at": "2026-05-27T17:14:11Z"},
                {"kind": "account.opened", "correlationId": "cor_demo", "at": "2026-05-27T17:14:13Z"},
                {"kind": "payment.settled", "correlationId": "cor_demo", "at": "2026-05-27T17:14:15Z"},
                {"kind": "notification.sent", "correlationId": "cor_demo", "at": "2026-05-27T17:14:16Z"},
            ]
        },
    )]

    items = [
        folder("OAuth", [
            request_item("Token", method="POST", raw_url=f"{base}/oauth2/token",
                         headers={"Content-Type": "application/json"},
                         body={"grant_type": "client_credentials"}, examples=oauth_examples),
        ]),
        folder("Health", [
            request_item("Health", method="GET", raw_url=f"{base}/health",
                         headers={"Accept": "application/json"}, examples=health_examples),
        ]),
        folder("Customers", [
            request_item("List customers", method="GET", raw_url=f"{base}/customers?limit=5",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=list_cust_examples),
            request_item("Create customer", method="POST", raw_url=f"{base}/customers",
                         headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                         body={"email": "demo@sourcefuse.example.com", "firstName": "Alex", "lastName": "Diaz"},
                         examples=create_cust_examples),
            request_item("Get customer", method="GET", raw_url=f"{base}/customers/:customerId",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=get_cust_examples),
            request_item("Delete customer", method="DELETE", raw_url=f"{base}/customers/:customerId",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=delete_cust_examples),
        ]),
        folder("KYC", [
            request_item("Submit KYC", method="POST", raw_url=f"{base}/customers/:customerId/kyc",
                         headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                         body={"documentType": "drivers_license"}, examples=kyc_post_examples),
            request_item("Get KYC", method="GET", raw_url=f"{base}/customers/:customerId/kyc",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=kyc_get_examples),
        ]),
        folder("Accounts", [
            request_item("Open account", method="POST", raw_url=f"{base}/customers/:customerId/accounts",
                         headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                         body={"type": "checking", "currency": "USD"}, examples=open_acc_examples),
            request_item("Get account", method="GET", raw_url=f"{base}/accounts/:accountId",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=get_acc_examples),
            request_item("Get account ledger", method="GET", raw_url=f"{base}/accounts/:accountId/ledger",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=ledger_examples),
        ]),
        folder("Payments", [
            request_item("Execute payment", method="POST", raw_url=f"{base}/payments",
                         headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                         body={"type": "ach_pull", "amount": "250.00", "currency": "USD"},
                         examples=pay_examples),
            request_item("Synthetic probe", method="POST", raw_url=f"{base}/payments/_synthetic",
                         headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                         body={"type": "synthetic_probe"}, examples=synth_examples),
        ]),
        folder("Audit", [
            request_item("List audit events", method="GET", raw_url=f"{base}/audit?correlationId=cor_demo",
                         headers={"Authorization": "Bearer {{authToken}}"}, examples=audit_examples),
        ]),
    ]
    return collection(
        "SourceFuse Platform — Mock",
        "Cloud mock of the SourceFuse platform — covers every endpoint used by the Customer Onboarding Regression Suite. "
        "Bound to a Postman mock server; the returned URL is wired into the 'SourceFuse — Mock' environment as baseUrl.",
        items,
    )


def build_core_banking_collection() -> dict:
    base = "{{baseUrl}}"
    items = [
        folder("Accounts", [
            request_item(
                "Get account", method="GET", raw_url=f"{base}/v2/accounts/:accountId",
                headers={"Authorization": "Bearer {{authToken}}"},
                examples=[
                    example("200 Active checking", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=200,
                            response_body={"id": "acc_4f3b1e22", "type": "checking", "status": "open", "balance": {"amount": "1250.42", "currency": "USD"}, "openedAt": "2025-12-01T08:30:00Z"}),
                    example("404 Not found", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=404,
                            response_body={"error": {"code": "account_not_found"}}),
                    example("409 Account closed", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=409,
                            response_body={"error": {"code": "account_closed", "closedAt": "2026-01-15T00:00:00Z"}}),
                    example("504 Upstream timeout", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=504,
                            response_body={"error": {"code": "upstream_timeout", "retryable": True}}),
                    example("206 Partial", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=206,
                            response_headers={"X-Partial-Reason": "core-ledger-degraded"},
                            response_body={"id": "acc_4f3b1e22", "balance": {"amount": "1250.42", "currency": "USD"}, "_partial": True}),
                    example("429 Rate limited", method="GET", raw_url=f"{base}/v2/accounts/:accountId", status_code=429,
                            response_headers={"Retry-After": "12"},
                            response_body={"error": {"code": "rate_limited", "retryAfterSeconds": 12}}),
                ],
            ),
            request_item(
                "Post ledger entry", method="POST", raw_url=f"{base}/v2/accounts/:accountId/ledger",
                headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                body={"direction": "credit", "amount": "100.00", "currency": "USD"},
                examples=[
                    example("201 Posted", method="POST", raw_url=f"{base}/v2/accounts/:accountId/ledger", status_code=201,
                            response_body={"id": "led_001", "balanceAfter": {"amount": "1350.42", "currency": "USD"}}),
                    example("422 Validation failure", method="POST", raw_url=f"{base}/v2/accounts/:accountId/ledger", status_code=422,
                            response_body={"error": {"code": "validation_error", "fields": [{"field": "amount", "rule": "positive"}]}}),
                ],
            ),
        ]),
    ]
    return collection("Core Banking — Mock", "Simulated core banking system with success / 404 / 409 / 504 / 206 / 429 examples.", items)


def build_payment_processor_collection() -> dict:
    base = "{{baseUrl}}"
    items = [
        folder("Charges", [
            request_item(
                "Create charge", method="POST", raw_url=f"{base}/v1/charges",
                headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                body={"amount": 25000, "currency": "usd"},
                examples=[
                    example("200 Captured", method="POST", raw_url=f"{base}/v1/charges", status_code=200,
                            response_body={"id": "ch_demo_001", "amount": 25000, "currency": "usd", "status": "succeeded"}),
                    example("402 Card declined", method="POST", raw_url=f"{base}/v1/charges", status_code=402,
                            response_body={"error": {"type": "card_error", "code": "card_declined", "decline_code": "generic_decline"}}),
                    example("503 Provider degraded", method="POST", raw_url=f"{base}/v1/charges", status_code=503,
                            response_body={"error": {"type": "api_error", "message": "Payment provider is unavailable"}}),
                    example("504 Timeout", method="POST", raw_url=f"{base}/v1/charges", status_code=504,
                            response_body={"error": {"type": "api_error", "code": "timeout"}}),
                    example("429 Rate limited", method="POST", raw_url=f"{base}/v1/charges", status_code=429,
                            response_headers={"Retry-After": "5"},
                            response_body={"error": {"type": "rate_limit_error"}}),
                ],
            ),
        ]),
    ]
    return collection("Payment Processor — Mock", "Stripe-shaped processor mock for the demo.", items)


def build_notifications_collection() -> dict:
    base = "{{baseUrl}}"
    items = [
        folder("Send", [
            request_item(
                "Send notification", method="POST", raw_url=f"{base}/v1/notifications",
                headers={"Authorization": "Bearer {{authToken}}", "Content-Type": "application/json"},
                body={"channel": "email", "template": "onboarding.welcome.v3"},
                examples=[
                    example("202 Queued", method="POST", raw_url=f"{base}/v1/notifications", status_code=202,
                            response_body={"notificationId": "ntf_001", "status": "queued"}),
                    example("400 Template not found", method="POST", raw_url=f"{base}/v1/notifications", status_code=400,
                            response_body={"error": {"code": "template_not_found"}}),
                    example("503 Channel offline", method="POST", raw_url=f"{base}/v1/notifications", status_code=503,
                            response_body={"error": {"code": "channel_offline"}}),
                    example("422 Invalid recipient", method="POST", raw_url=f"{base}/v1/notifications", status_code=422,
                            response_body={"error": {"code": "validation_error", "fields": [{"field": "to", "rule": "email"}]}}),
                ],
            ),
        ]),
    ]
    return collection("Notification Service — Mock", "Multi-channel notifications mock.", items)


def build_legacy_collection() -> dict:
    base = "{{baseUrl}}"
    items = [
        folder("Customer", [
            request_item(
                "Get legacy customer", method="GET", raw_url=f"{base}/customers/:externalId",
                headers={"X-Legacy-API-Key": "{{authToken}}"},
                examples=[
                    example("200 Full record", method="GET", raw_url=f"{base}/customers/:externalId", status_code=200,
                            response_body={"externalId": "ext_demo", "firstName": "Alex", "lastName": "Diaz", "address": {"city": "San Francisco", "state": "CA"}, "legacyAccountNumber": "0001234567"}),
                    example("206 Partial", method="GET", raw_url=f"{base}/customers/:externalId", status_code=206,
                            response_headers={"X-Partial-Reason": "mainframe-cics-region-degraded"},
                            response_body={"externalId": "ext_demo", "firstName": "Alex", "_partial": True, "_missing": ["address"]}),
                    example("504 Mainframe timeout", method="GET", raw_url=f"{base}/customers/:externalId", status_code=504,
                            response_body={"error": {"code": "mainframe_timeout", "region": "CICSPROD1"}}),
                    example("429 Throttled", method="GET", raw_url=f"{base}/customers/:externalId", status_code=429,
                            response_headers={"Retry-After": "60"},
                            response_body={"error": {"code": "legacy_throttled"}}),
                ],
            ),
        ]),
    ]
    return collection("Legacy Customer Platform — Mock", "Legacy COBOL-backed platform via REST shim, with flaky behaviors.", items)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

PLAN = [
    ("SourceFuse Platform — Mock", build_platform_collection, "baseUrl"),
    ("Core Banking — Mock", build_core_banking_collection, "coreBankingUrl"),
    ("Payment Processor — Mock", build_payment_processor_collection, "paymentProcessorUrl"),
    ("Notification Service — Mock", build_notifications_collection, "notificationsUrl"),
    ("Legacy Customer Platform — Mock", build_legacy_collection, "legacyCustomerUrl"),
]


def yaml_dump_env(env: dict) -> str:
    """Tiny YAML emitter matching the project's existing format."""
    lines = [f"name: {env['name']}", f"color: \"{env['color']}\"", "values:"]
    for v in env["values"]:
        lines.append(f"  - key: {v['key']}")
        val = v["value"]
        if isinstance(val, str):
            esc = val.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    value: "{esc}"')
        else:
            lines.append(f"    value: {val}")
        lines.append(f"    enabled: {'true' if v.get('enabled', True) else 'false'}")
        if v.get("type"):
            lines.append(f"    type: {v['type']}")
    return "\n".join(lines) + "\n"


def main():
    print("Building mock collections + servers in workspace", WORKSPACE_ID)
    env_values = []

    for name, builder, env_var in PLAN:
        # Wipe any prior version so this is idempotent
        existing = find_existing(name)
        if existing:
            print(f"  ✗ removing existing collection: {name} ({existing})")
            delete_collection(existing)
            # also delete any mock bound to that collection (handled below by enumerating mocks)

        coll_def = builder()
        print(f"  → pushing collection: {name}")
        uid, _id = create_collection(coll_def)
        time.sleep(1)  # small delay to allow indexing

        mock_name = f"{name} — server"
        # Remove existing mock with this name
        for m in list_mocks():
            if m.get("name") == mock_name:
                _req("DELETE", f"/mocks/{m['uid']}")
        print(f"  → creating mock server: {mock_name}")
        mock = create_mock(uid, mock_name)
        mock_url = mock.get("mockUrl") or mock.get("url") or ""
        print(f"     URL: {mock_url}")
        env_values.append((env_var, mock_url, name, uid, mock.get("uid")))

    # Write the Mock environment
    env = {
        "name": "SourceFuse — Mock",
        "color": "#6f42c1",
        "values": [
            {"key": k, "value": v, "enabled": True}
            for k, v, *_ in env_values
        ] + [
            {"key": "authToken", "value": "mock-bearer-token", "enabled": True, "type": "secret"},
            {"key": "tenantId", "value": "tnt_mock_001", "enabled": True},
            {"key": "kycProvider", "value": "mock", "enabled": True},
            {"key": "p95BudgetMs", "value": "1500", "enabled": True},
            {"key": "featureFlag.aiAssertions", "value": "true", "enabled": True},
        ],
    }
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    out = ENV_DIR / "SourceFuse — Mock.environment.yaml"
    out.write_text(yaml_dump_env(env))
    print(f"\nWrote environment: {out}")

    # Print summary
    print("\nMock URLs:")
    for env_var, url, name, _coll_uid, _mock_uid in env_values:
        print(f"  {env_var:24s} → {url}   ({name})")


if __name__ == "__main__":
    main()
