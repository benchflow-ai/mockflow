"""Users API routes — users.* methods."""

from __future__ import annotations

import time
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import json

from mock_slack.models import SlackUser, Workspace
from .deps import (
    get_db,
    resolve_workspace_id,
    encode_cursor,
    decode_cursor,
    guard_impersonation,
    resolve_auth_local_id,
)
from .schemas import (
    UserSchema,
    UserProfileSchema,
    UsersListResponse,
    UserInfoResponse,
)

router = APIRouter()


def _resolved_avatar_url(user: SlackUser) -> str:
    if user.avatar_url and user.avatar_url != "/static/profile_picture.jpg":
        return user.avatar_url
    return ""


def _user_to_schema(user: SlackUser, db: Session | None = None) -> UserSchema:
    # Get workspace team_id
    team_id = ""
    if db is not None:
        ws = db.query(Workspace).filter(Workspace.id == user.workspace_id).first()
        team_id = ws.team_id if ws else ""

    # Build first/last name from real_name
    name_parts = (user.real_name or "").split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    avatar_url = _resolved_avatar_url(user)

    # Build profile dict (USLACKBOT gets always_active=True)
    profile_dict = {
        "real_name": user.real_name or "",
        "real_name_normalized": user.real_name or "",
        "display_name": user.name or "",
        "display_name_normalized": user.name or "",
        "first_name": first_name,
        "last_name": last_name,
        "email": user.email or "",
        "title": user.title or "",
        "phone": "",
        "skype": "",
        "status_text": user.status_text or "",
        "status_text_canonical": "",
        "status_emoji": user.status_emoji or "",
        "status_emoji_display_info": [],
        "status_expiration": 0,
        "tz": user.tz or "America/Los_Angeles",
        "team": team_id,
        "image_24": avatar_url,
        "image_32": avatar_url,
        "image_48": avatar_url,
        "image_72": avatar_url,
    }
    if user.id == "USLACKBOT":
        profile_dict["always_active"] = True

    return UserSchema(
        id=user.id,
        name=user.name,
        real_name=user.real_name or "",
        deleted=user.is_deleted,
        is_admin=user.is_admin,
        is_bot=user.is_bot,
        is_app_user=False,
        is_email_confirmed=True,
        is_owner=False,
        is_primary_owner=False,
        is_restricted=False,
        is_ultra_restricted=False,
        updated=int(time.time()),
        team_id=team_id,
        tz=user.tz or "America/Los_Angeles",
        tz_label="Pacific Daylight Time",
        tz_offset=-25200,
        who_can_share_contact_card="EVERYONE",
        enterprise_user=None,
        profile=UserProfileSchema(**{k: v for k, v in profile_dict.items() if k in UserProfileSchema.model_fields}),
    )


def _user_to_dict(user: SlackUser, db: Session | None = None) -> dict:
    """Return user as dict, adding always_active for USLACKBOT."""
    schema = _user_to_schema(user, db)
    d = schema.model_dump()
    if user.id == "USLACKBOT":
        d["profile"]["always_active"] = True
    return d


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})


@router.get("/users.list")
def users_list(
    limit: int = Query(200, ge=1, le=1000),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    import time as _time

    q = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id,
        SlackUser.is_deleted == False,
    )

    # Cursor-based pagination: cursor encodes "after:<user_id>"
    if cursor:
        payload = decode_cursor(cursor)
        if payload and payload.startswith("after:"):
            after_uid = payload[len("after:"):]
            q = q.filter(SlackUser.id > after_uid)

    q = q.order_by(SlackUser.id.asc())
    users = q.limit(limit + 1).all()

    has_more = len(users) > limit
    users = users[:limit]

    next_cursor = encode_cursor(f"after:{users[-1].id}") if has_more and users else ""
    return {
        "ok": True,
        "members": [_user_to_dict(u, db) for u in users],
        "cache_ts": int(_time.time()),
        "response_metadata": {"next_cursor": next_cursor},
    }


@router.get("/users.info")
def users_info(
    user: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    u = (
        db.query(SlackUser)
        .filter(SlackUser.id == user, SlackUser.workspace_id == workspace_id)
        .first()
    )
    if not u:
        return _slack_error("user_not_found")
    return {"ok": True, "user": _user_to_dict(u, db)}


@router.get("/users.lookupByEmail")
def users_lookup_by_email(
    email: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    u = (
        db.query(SlackUser)
        .filter(SlackUser.email == email, SlackUser.workspace_id == workspace_id)
        .first()
    )
    if not u:
        return _slack_error("users_not_found")
    return {"ok": True, "user": _user_to_dict(u, db)}


@router.get("/users.profile.get")
def users_profile_get(
    request: Request,
    user: str | None = Query(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    # auth: with no explicit user, "self" is the verified token's
    # RESOLVED local identity (sub, else email-claim fallback). Reading
    # ANOTHER user's profile by explicit id stays a legitimate directory
    # read, like real Slack.
    if user is None:
        user = resolve_auth_local_id(request, db)

    if user:
        u = (
            db.query(SlackUser)
            .filter(SlackUser.id == user, SlackUser.workspace_id == workspace_id)
            .first()
        )
    else:
        # Return first non-bot user's profile
        u = (
            db.query(SlackUser)
            .filter(
                SlackUser.workspace_id == workspace_id,
                SlackUser.is_bot == False,
                SlackUser.id != "USLACKBOT",
            )
            .first()
        )
    if not u:
        return _slack_error("user_not_found")
    profile = _user_to_schema(u, db).profile
    return {"ok": True, "profile": profile.model_dump()}


@router.post("/users.profile.set")
async def users_profile_set(
    request: Request,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    user_id = data.get("user")

    # auth: a profile WRITE may only target the verified token's own
    # identity (its sub or the RESOLVED local id from the email-claim
    # fallback). An explicit mismatching `user` is impersonation (contract
    # 403, reported to auth); the effective target is always the
    # resolved local identity.
    auth_sub = getattr(request.state, "auth_user_id", None)
    if auth_sub is not None:
        guard_impersonation(request, user_id, db)
        user_id = resolve_auth_local_id(request, db)

    if user_id:
        u = (
            db.query(SlackUser)
            .filter(SlackUser.id == user_id, SlackUser.workspace_id == workspace_id)
            .first()
        )
    else:
        # Update first non-bot user's profile
        u = (
            db.query(SlackUser)
            .filter(SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False)
            .first()
        )

    if not u:
        return _slack_error("user_not_found")

    profile_data = data.get("profile", {})
    if isinstance(profile_data, str):
        try:
            profile_data = json.loads(profile_data)
        except:
            pass

    if isinstance(profile_data, dict):
        if "status_text" in profile_data:
            u.status_text = profile_data["status_text"]
        if "status_emoji" in profile_data:
            u.status_emoji = profile_data["status_emoji"]

    db.commit()

    profile = _user_to_schema(u, db).profile
    return {
        "ok": True,
        "username": u.name,
        "profile": profile.model_dump(),
        "warning": "missing_charset",
        "response_metadata": {"warnings": ["missing_charset"]},
    }


@router.post("/users.setPresence")
async def users_set_presence(
    request: Request,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    presence = data.get("presence", "auto")

    # auth: presence is set on the verified token's RESOLVED local
    # identity (sub, else email-claim fallback), never on the legacy "first
    # non-bot user" fallback.
    auth_local = resolve_auth_local_id(request, db)
    if auth_local is not None:
        u = (
            db.query(SlackUser)
            .filter(SlackUser.id == auth_local, SlackUser.workspace_id == workspace_id)
            .first()
        )
    else:
        u = (
            db.query(SlackUser)
            .filter(
                SlackUser.workspace_id == workspace_id,
                SlackUser.is_bot == False,
                SlackUser.id != "USLACKBOT",
            )
            .first()
        )
    if u:
        u.presence = presence
        db.commit()

    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}


@router.get("/users.getPresence")
async def users_get_presence(
    request: Request,
    user: str = Query(None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    # auth: with no explicit user, "self" is the verified token's
    # RESOLVED local identity (sub, else email-claim fallback). Explicit
    # reads of other users' presence stay legitimate, like real Slack.
    if not user:
        user = resolve_auth_local_id(request, db)

    if user:
        u = (
            db.query(SlackUser)
            .filter(SlackUser.id == user, SlackUser.workspace_id == workspace_id)
            .first()
        )
    else:
        u = (
            db.query(SlackUser)
            .filter(SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False)
            .first()
        )

    if not u:
        return _slack_error("user_not_found")

    return {
        "ok": True,
        "presence": u.presence,
    }
