from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

API_VERSION = "1.0"


class APIProtocolError(Exception):
    pass


@dataclass
class APIRequest:
    api_version: str
    request_id: str
    action: str
    payload: Dict[str, Any]
    legacy: bool = False


def normalise_request(raw: Dict[str, Any]) -> APIRequest:
    if not isinstance(raw, dict):
        raise APIProtocolError("Top-level JSON must be an object")

    if "api_version" in raw and "request_id" in raw:
        api_version = raw.get("api_version")
        request_id = str(raw.get("request_id"))
        action = raw.get("action")
        payload = raw.get("payload") or {}
        if api_version != API_VERSION:
            raise APIProtocolError(f"Unsupported api_version {api_version}")
        if not isinstance(action, str) or not action:
            raise APIProtocolError("Missing or invalid 'action'")
        if not isinstance(payload, dict):
            raise APIProtocolError("'payload' must be an object")
        return APIRequest(
            api_version=api_version,
            request_id=request_id,
            action=action,
            payload=payload,
            legacy=False,
        )

    # Legacy shim
    legacy_payload = dict(raw)
    action = legacy_payload.pop("action", None) or legacy_payload.pop("type", None)
    if not isinstance(action, str) or not action:
        raise APIProtocolError("Legacy request missing 'action'")
    return APIRequest(
        api_version=API_VERSION,
        request_id="legacy",
        action=action,
        payload=legacy_payload,
        legacy=True,
    )


def make_response(
    req: Optional[APIRequest],
    status: str,
    payload: Dict[str, Any],
    error: Optional[str],
) -> Dict[str, Any]:
    api_version = API_VERSION
    request_id = req.request_id if req is not None else "unknown"
    action = req.action if req is not None else "unknown"
    return {
        "api_version": api_version,
        "request_id": request_id,
        "action": action,
        "status": status,
        "payload": payload,
        "error": error,
    }
