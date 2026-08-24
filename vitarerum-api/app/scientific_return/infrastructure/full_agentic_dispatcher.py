from __future__ import annotations

import base64
import json

import httpx

from app.scientific_return.domain.full_agentic_models import (
    FullAgenticInvestigationId,
)


class DatabaseQueueDispatcher:
    """The investigation row itself is the durable queue for a polling worker."""

    async def enqueue(self, investigation_id: FullAgenticInvestigationId) -> None:
        del investigation_id


class CloudTasksDispatcher:
    """Cloud Tasks REST adapter using the runtime service-account token."""

    def __init__(
        self,
        *,
        queue_url: str,
        worker_url: str,
        service_account: str,
        worker_token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._queue_url = queue_url
        self._worker_url = worker_url
        self._service_account = service_account
        self._worker_token = worker_token
        self._timeout = timeout_seconds

    async def enqueue(self, investigation_id: FullAgenticInvestigationId) -> None:
        if not all(
            (
                self._queue_url,
                self._worker_url,
                self._service_account,
                self._worker_token,
            )
        ):
            raise RuntimeError("Cloud Tasks dispatcher is not fully configured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            token_response = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/"
                "service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
            )
            token_response.raise_for_status()
            access_token = str(token_response.json()["access_token"])
            body = base64.b64encode(
                json.dumps(
                    {"investigationId": str(investigation_id)},
                    separators=(",", ":"),
                ).encode()
            ).decode()
            response = await client.post(
                self._queue_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "task": {
                        "httpRequest": {
                            "httpMethod": "POST",
                            "url": self._worker_url,
                            "headers": {
                                "Content-Type": "application/json",
                                "X-Worker-Token": self._worker_token,
                            },
                            "body": body,
                            "oidcToken": {
                                "serviceAccountEmail": self._service_account,
                                "audience": self._worker_url,
                            },
                        }
                    }
                },
            )
            response.raise_for_status()
