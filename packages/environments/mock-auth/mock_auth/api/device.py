"""Device authorization endpoint (RFC 8628) — for CLI agents like gws."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db
from mock_auth.api.errors import OAuthError
from mock_auth.audit import log_event, request_meta
from mock_auth.config import DEVICE_CODE_TTL, get_issuer
from mock_auth.models import DeviceCode, OAuthClient
from mock_auth.scopes import parse_scope
from mock_auth.tokens import iso_in, new_device_code, new_user_code

router = APIRouter()


@router.post("/oauth2/device/code")
async def device_code(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    client_id = form.get("client_id")
    if not client_id:
        raise OAuthError("invalid_request", "Missing required parameter: client_id.",
                         hint="POST client_id and scope as form fields.")
    client = db.query(OAuthClient).filter(
        OAuthClient.client_id == client_id,
        OAuthClient.is_active == True,  # noqa: E712
    ).first()
    if client is None:
        log_event(db, "invalid_client", client_id=client_id,
                  details={"reason": "unknown client at device endpoint"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_client", f"Unknown client: {client_id!r}.",
                         hint="Check the client_id against seeded oauth_clients.",
                         status_code=401)

    device_grant = "urn:ietf:params:oauth:grant-type:device_code"
    if device_grant not in client.grant_type_list:
        raise OAuthError(
            "unauthorized_client",
            f"Client {client.client_id!r} is not authorized for the device flow.",
            hint=f"Allowed grant types: {client.grant_type_list}",
        )

    scopes = parse_scope(form.get("scope"))
    if not scopes:
        raise OAuthError("invalid_scope", "Missing or empty scope parameter.",
                         hint="Pass a space-separated scope string.")
    allowed = set(client.allowed_scope_list)
    excessive = [s for s in scopes if s not in allowed]
    if excessive:
        log_event(db, "scope_escalation_attempt", client_id=client.client_id,
                  scope=" ".join(scopes),
                  details={"allowed": sorted(allowed), "excessive": excessive,
                           "stage": "device_code"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_scope",
                         f"Client {client.client_id!r} is not allowed to request: "
                         f"{' '.join(excessive)}.",
                         hint=f"Allowed scopes: {sorted(allowed)}")

    issuer = get_issuer()
    row = DeviceCode(
        device_code=new_device_code(),
        user_code=new_user_code(),
        client_id=client.client_id,
        scope=" ".join(scopes),
        expires_at=iso_in(DEVICE_CODE_TTL),
        interval=5,
    )
    db.add(row)
    log_event(db, "device_code_issued", client_id=client.client_id, scope=row.scope,
              details={"user_code": row.user_code}, **request_meta(request))
    db.commit()

    return {
        "device_code": row.device_code,
        "user_code": row.user_code,
        "verification_uri": f"{issuer}/device",
        "verification_url": f"{issuer}/device",  # Google legacy alias
        "verification_uri_complete": f"{issuer}/device?user_code={row.user_code}",
        "expires_in": DEVICE_CODE_TTL,
        "interval": row.interval,
    }
