"""ERPNext connector implementing the VendorOps execution adapter contract.

The connector is deliberately transport-focused: VendorOps owns authorization,
approval, idempotency and execution state; ERPNext owns the external document.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.agent.execution import ExecutionAdapter
from app.agent.tool_registry import ToolDefinition


class ERPNextConnectorError(RuntimeError):
    """Raised when ERPNext cannot safely service a connector operation."""


class ERPNextConnector(ExecutionAdapter):
    """Minimal ERPNext REST connector for governed vendor-invoice execution."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        *,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not api_key.strip() or not api_secret.strip():
            raise ValueError("api_key and api_secret must not be empty")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"token {api_key}:{api_secret}"}
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def healthcheck(self) -> dict[str, Any]:
        response = self._client.get(
            f"{self.base_url}/api/method/frappe.auth.get_logged_user",
            headers=self._headers,
        )
        if response.status_code >= 400:
            raise ERPNextConnectorError(
                f"ERPNext healthcheck failed with HTTP {response.status_code}"
            )
        return {"healthy": True, "user": response.json().get("message")}

    @staticmethod
    def _idempotency_remark(idempotency_key: str) -> str:
        return f"VendorOps-Idempotency-Key: {idempotency_key}"

    def execute(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if tool.name != "create_vendor_invoice":
            raise ERPNextConnectorError(f"Unsupported ERPNext tool: {tool.name}")

        # Use the standard Purchase Invoice remarks field so the reference
        # deployment needs no custom ERPNext app or custom DocType field.
        invoice = {
            "doctype": "Purchase Invoice",
            "supplier": payload["vendor_id"],
            "currency": payload["currency"],
            "grand_total": payload["amount"],
            "remarks": self._idempotency_remark(idempotency_key),
        }
        response = self._client.post(
            f"{self.base_url}/api/resource/Purchase Invoice",
            headers={**self._headers, "Content-Type": "application/json"},
            json=invoice,
        )
        if response.status_code >= 400:
            raise ERPNextConnectorError(
                f"ERPNext invoice creation failed with HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        message = response.json().get("data") or {}
        external_id = message.get("name")
        if not external_id:
            raise ERPNextConnectorError("ERPNext did not return a Purchase Invoice name")
        return {
            "external_id": external_id,
            "status": message.get("status", "created"),
            "amount": payload["amount"],
            "idempotency_key": idempotency_key,
        }

    def verify(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        if tool.name != "create_vendor_invoice":
            raise ERPNextConnectorError(f"Unsupported ERPNext tool: {tool.name}")
        external_id = output.get("external_id")
        if not external_id:
            return {"verified": False, "reason": "missing ERPNext document id"}

        response = self._client.get(
            f"{self.base_url}/api/resource/Purchase Invoice/{external_id}",
            headers=self._headers,
        )
        if response.status_code >= 400:
            return {
                "verified": False,
                "reason": f"ERPNext verification returned HTTP {response.status_code}",
            }
        data = response.json().get("data") or {}
        verified = (
            data.get("name") == external_id
            and data.get("supplier") == payload["vendor_id"]
            and float(data.get("grand_total", 0)) == float(payload["amount"])
            and data.get("currency") == payload["currency"]
            and data.get("remarks") == self._idempotency_remark(output["idempotency_key"])
        )
        return {"verified": verified, "external_id": external_id}

    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        """Find an invoice created before an ambiguous retry."""
        response = self._client.get(
            f"{self.base_url}/api/resource/Purchase Invoice",
            headers=self._headers,
            params={
                "filters": (
                    f'[["remarks","=","{self._idempotency_remark(idempotency_key)}"]]'
                )
            },
        )
        if response.status_code >= 400:
            raise ERPNextConnectorError(
                f"ERPNext reconciliation failed with HTTP {response.status_code}"
            )
        rows = response.json().get("data") or []
        return rows[0] if rows else None
