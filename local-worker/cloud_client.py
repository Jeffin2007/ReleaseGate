"""
Outbound Authenticated Cloud Control Plane Client for the Local Worker.
According to the ReleaseGate Architecture Baseline v1.0:
- The local worker is never publicly exposed.
- The local worker initiates outbound authenticated communication with the Cloud Control Plane.
- Only sanitized metadata, content hashes, opaque artifact references, and profiling summaries
  are transmitted to the Cloud Control Plane. Raw dataset bytes never cross this boundary.
"""

from typing import Any, Callable, Dict, Optional
import httpx

try:
    from local_worker.ingestion_service import SanitizedIngestionPayload
except ImportError:
    from .ingestion_service import SanitizedIngestionPayload


class CloudClientError(Exception):
    """Raised when outbound communication with the Cloud Control Plane fails."""
    pass


class CloudControlPlaneClient:
    """
    Outbound client used by the local worker to register sanitized dataset metadata
    with the FastAPI Cloud Control Plane.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        worker_api_token: str = "local-worker-outbound-token",
        timeout_seconds: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.worker_api_token = worker_api_token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.worker_api_token}",
            "X-ReleaseGate-Plane": "local-worker-outbound",
            "Content-Type": "application/json",
        }

    def register_ingested_dataset(
        self,
        payload: SanitizedIngestionPayload,
        is_new_version_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Send sanitized dataset metadata and profiling summary outbound to the Cloud Control Plane.
        Strictly enforces that no raw dataset bytes or host filesystem paths are included.
        """
        # Safety invariant verification before outbound transmission
        if not payload.local_artifact_ref.startswith("artifact://local/datasets/"):
            raise CloudClientError(
                "Security violation: Outbound payload contains non-opaque artifact reference"
            )

        body: Dict[str, Any] = {
            "dataset_id": str(payload.dataset_id) if is_new_version_only else str(payload.dataset_id),
            "dataset_name": payload.dataset_name,
            "description": payload.description,
            "content_hash": payload.content_hash,
            "file_format": payload.file_format,
            "file_size": payload.file_size,
            "local_artifact_ref": payload.local_artifact_ref,
            "profile": payload.profile,
        }

        with httpx.Client(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.post("/api/v1/datasets/register-metadata", json=body)
            if response.status_code not in (200, 201):
                raise CloudClientError(
                    f"Cloud Control Plane rejected metadata registration "
                    f"(HTTP {response.status_code}): {response.text}"
                )
            return response.json()

    def record_inspection_run(
        self,
        payload: Any,
        organization_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Send sanitized inspection run and findings outbound to the Cloud Control Plane.
        Strictly enforces that no raw dataset values or sensitive tokens are included.
        """
        if hasattr(payload, "model_dump"):
            body = payload.model_dump(mode="json")
        elif isinstance(payload, dict):
            body = payload
        else:
            raise CloudClientError(f"Unsupported inspection payload type: {type(payload)}")

        headers = self._get_headers()
        params = {}
        if organization_id:
            headers["X-Organization-ID"] = str(organization_id)
            params["organization_id"] = str(organization_id)

        with httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.post("/api/v1/inspections/record", json=body, params=params)
            if response.status_code not in (200, 201):
                raise CloudClientError(
                    f"Cloud Control Plane rejected inspection run persistence "
                    f"(HTTP {response.status_code}): {response.text}"
                )
            return response.json()
