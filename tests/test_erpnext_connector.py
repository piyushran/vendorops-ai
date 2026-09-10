from __future__ import annotations

import json
from typing import Any

import httpx

from app.integrations.erpnext import ERPNextConnector


class FakeTool:
    name = "create_vendor_invoice"


def test_create_vendor_invoice_uses_token_auth_and_idempotency_reference() -> None:
    seen: dict[str, Any] = {"methods": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["methods"].append(request.method)
        seen["authorization"] = request.headers["Authorization"]
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"data": {"name": "ACC-PINV-0001", "status": "Draft"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ERPNextConnector("http://erpnext.test", "key", "secret", client=client)

    result = connector.execute(
        FakeTool(),
        {"vendor_id": "SUP-0001", "amount": 1250.0, "currency": "INR"},
        idempotency_key="invoice-write-1",
    )

    assert seen["methods"] == ["GET", "POST"]
    assert seen["authorization"] == "token key:secret"
    assert seen["json"]["doctype"] == "Purchase Invoice"
    assert seen["json"]["remarks"] == "VendorOps-Idempotency-Key: invoice-write-1"
    assert result["external_id"] == "ACC-PINV-0001"


def test_create_vendor_invoice_reuses_existing_idempotency_match_without_post() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": "ACC-PINV-0009",
                        "status": "Draft",
                        "grand_total": 1250.0,
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ERPNextConnector("http://erpnext.test", "key", "secret", client=client)

    result = connector.execute(
        FakeTool(),
        {"vendor_id": "SUP-0001", "amount": 1250.0, "currency": "INR"},
        idempotency_key="invoice-write-9",
    )

    assert calls == ["GET"]
    assert result["external_id"] == "ACC-PINV-0009"
    assert result["reused_existing"] is True


def test_find_by_idempotency_key_supports_ambiguous_outcome_reconciliation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/resource/Purchase Invoice")
        assert "invoice-write-2" in str(request.url)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": "ACC-PINV-0002",
                        "remarks": "VendorOps-Idempotency-Key: invoice-write-2",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ERPNextConnector("http://erpnext.test", "key", "secret", client=client)

    result = connector.find_by_idempotency_key("invoice-write-2")

    assert result is not None
    assert result["name"] == "ACC-PINV-0002"


def test_verify_checks_external_document_identity_and_amount() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "name": "ACC-PINV-0003",
                    "supplier": "SUP-0003",
                    "grand_total": 500.0,
                    "currency": "INR",
                    "remarks": "VendorOps-Idempotency-Key: invoice-write-3",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ERPNextConnector("http://erpnext.test", "key", "secret", client=client)

    result = connector.verify(
        FakeTool(),
        {"vendor_id": "SUP-0003", "amount": 500.0, "currency": "INR"},
        {"external_id": "ACC-PINV-0003", "idempotency_key": "invoice-write-3"},
    )

    assert result == {"verified": True, "external_id": "ACC-PINV-0003"}
