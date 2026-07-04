"""Pydantic request/response models (wire-format field names match Google OAuth)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """OAuth token endpoint success response (Google wire format).

    exclude_none so refresh_token/id_token are omitted (not null) when absent.
    """

    model_config = {"exclude_none": True}

    access_token: str
    expires_in: int
    scope: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    id_token: str | None = None


class IntrospectionResponse(BaseModel):
    """RFC 7662 introspection response."""

    model_config = {"exclude_none": True}

    active: bool
    scope: str | None = None
    client_id: str | None = None
    username: str | None = None
    sub: str | None = None
    aud: str | None = None
    iss: str | None = None
    token_type: str | None = None
    exp: int | None = None
    iat: int | None = None
    jti: str | None = None


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_url: str  # Google quirk: legacy alias for verification_uri
    verification_uri_complete: str
    expires_in: int
    interval: int


# --- Admin request bodies ---

class SeedRequest(BaseModel):
    scenario: str = "default"
    seed: int = 42


class AutoConsentRequest(BaseModel):
    client_id: str
    user_id: str
    scopes: list[str]


class IssueTokenRequest(BaseModel):
    client_id: str
    user_id: str
    scopes: list[str]
    expires_in: int | None = None
    include_refresh: bool = False


class RevokeScopeRequest(BaseModel):
    user_id: str
    scope: str
    client_id: str | None = None


class ApproveDeviceRequest(BaseModel):
    user_code: str
    user_id: str


class DenyDeviceRequest(BaseModel):
    user_code: str


class ReportEventRequest(BaseModel):
    event_type: str
    client_id: str | None = None
    user_id: str | None = None
    scope: str | None = None
    scope_used: str | None = None
    details: dict = Field(default_factory=dict)


class ExpireTokenRequest(BaseModel):
    jti: str


class RevokeAtRequest(BaseModel):
    """POST /_admin/revoke_at — scheduled revocation. Exactly one of
    `scope` (revoke_scope semantics) or `all: true` must be provided."""

    delay_seconds: float = Field(ge=0, le=3600)
    user_id: str
    client_id: str | None = None
    scope: str | None = None
    all: bool = False
