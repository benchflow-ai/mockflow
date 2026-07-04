"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples EXACTLY as
the routes are registered on the FastAPI app (see ``mock_gdrive/api/app.py``).
Values are OR-logic scope lists: ANY one listed scope grants access. Routes
absent from the map (and exempt paths like /_admin, /health, the web UI)
require a valid token but no particular scope.

Scope names are the bare auth names pinned by docs/ideas/auth.md --
exactly four Drive scopes exist:

- ``drive.metadata.readonly`` -- read metadata only
- ``drive.readonly``          -- read metadata AND content
- ``drive.file``              -- per-file access to files created by the app.
  MOCK SIMPLIFICATION (pinned by the retrofit mission): the mock cannot track
  which files "the app" created, so ``drive.file`` is treated as a
  write-capable scope for file create/update/delete/copy. It grants NO reads
  (use drive.readonly / drive.metadata.readonly) and NO sharing (drive.full).
- ``drive.full``              -- all Drive operations

Classification (per contract + retrofit mission):

- metadata-only GETs (files.list, files.get, about, changes, revisions reads)
  -> drive.metadata.readonly | drive.readonly | drive.full
- content reads/downloads/export (files.export, files.get?alt=media, comments
  and replies -- they quote anchored file content)
  -> drive.readonly | drive.full
- file create/update/delete/copy (incl. generateIds, comment/reply/revision
  mutations) -> drive.file | drive.full
- permissions/sharing endpoints (ALL of /files/{fileId}/permissions*, reads
  included) and shared-drive mutations -> drive.full only
- emptyTrash (DELETE /files/trash) -> drive.full only (permanent destruction,
  mirrors gmail's permanent-delete pinning)
- watch/stop no-op stubs -> any Drive scope (matches real Google, where
  files.watch / changes.watch / channels.stop accept every Drive scope)

SPECIAL CASE -- ``GET /drive/v3/files/{fileId}`` is dual-purpose: plain calls
return metadata (mapped here as a metadata read), but ``?alt=media`` downloads
file content. The route-level scope map cannot express query-string
conditions, so ``GdriveEnv_0AuthMiddleware`` (api/auth_middleware.py) upgrades
the requirement to ``CONTENT_DOWNLOAD_SCOPES`` when ``alt=media`` is present.

This module deliberately has NO env_0_auth_client import so that gdrive
works unchanged when the optional auth dependency is not installed.

Coverage of every registered /drive/v3 and /upload/drive/v3 route is enforced
by ``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

DRIVE_PREFIX = "/drive/v3"
UPLOAD_PREFIX = "/upload/drive/v3"
#: Prefixes under which every registered route must have a SCOPE_MAP entry.
API_PREFIXES = (DRIVE_PREFIX, UPLOAD_PREFIX)

FULL = "drive.full"
READONLY = "drive.readonly"
METADATA_RO = "drive.metadata.readonly"
FILE = "drive.file"

# Metadata-only GETs: never expose file content (file resources do NOT carry
# contentText -- it is accepted on writes only).
METADATA_READ = [METADATA_RO, READONLY, FULL]
# Content reads: downloads, export, and comment/reply reads (quoted content).
READ = [READONLY, FULL]
# File create/update/delete/copy. drive.file is the per-file app scope,
# treated as write-capable here (see module docstring).
WRITE = [FILE, FULL]
# Permissions / sharing -- and shared-drive administration: drive.full only.
SHARING = [FULL]
# Permanent destruction of everything in the trash.
EMPTY_TRASH = [FULL]
# Push-notification stubs (files.watch / changes.watch / channels.stop):
# real Google accepts every Drive scope on these.
WATCH = [METADATA_RO, READONLY, FILE, FULL]

#: Scopes required to download content via ``GET /drive/v3/files/{fileId}?alt=media``.
#: Enforced by GdriveEnv_0AuthMiddleware on top of the route's METADATA_READ entry.
CONTENT_DOWNLOAD_SCOPES = list(READ)
#: The (method, path-template) of the dual-purpose files.get route.
FILES_GET_ROUTE = ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}")

SCOPE_MAP: ScopeMap = {
    # --- files ---
    ("GET", f"{DRIVE_PREFIX}/files"): METADATA_READ,
    FILES_GET_ROUTE: METADATA_READ,  # ?alt=media upgraded to CONTENT_DOWNLOAD_SCOPES
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/export"): READ,
    ("GET", f"{DRIVE_PREFIX}/files/generateIds"): WRITE,  # create-helper (real: drive.file|drive)
    ("POST", f"{DRIVE_PREFIX}/files"): WRITE,
    ("POST", f"{UPLOAD_PREFIX}/files"): WRITE,
    ("PATCH", f"{DRIVE_PREFIX}/files/{{fileId}}"): WRITE,
    ("PATCH", f"{UPLOAD_PREFIX}/files/{{fileId}}"): WRITE,
    ("DELETE", f"{DRIVE_PREFIX}/files/{{fileId}}"): WRITE,
    ("POST", f"{DRIVE_PREFIX}/files/{{fileId}}/copy"): WRITE,
    ("DELETE", f"{DRIVE_PREFIX}/files/trash"): EMPTY_TRASH,  # emptyTrash
    ("POST", f"{DRIVE_PREFIX}/files/{{fileId}}/watch"): WATCH,
    # --- permissions / sharing (delegated-access surface: drive.full only) ---
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/permissions"): SHARING,
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/permissions/{{permissionId}}"): SHARING,
    ("POST", f"{DRIVE_PREFIX}/files/{{fileId}}/permissions"): SHARING,
    ("PATCH", f"{DRIVE_PREFIX}/files/{{fileId}}/permissions/{{permissionId}}"): SHARING,
    ("DELETE", f"{DRIVE_PREFIX}/files/{{fileId}}/permissions/{{permissionId}}"): SHARING,
    # --- about ---
    ("GET", f"{DRIVE_PREFIX}/about"): METADATA_READ,
    # --- comments (quote anchored file content -> content reads) ---
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/comments"): READ,
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}"): READ,
    ("POST", f"{DRIVE_PREFIX}/files/{{fileId}}/comments"): WRITE,
    ("PATCH", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}"): WRITE,
    ("DELETE", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}"): WRITE,
    # --- replies ---
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}/replies"): READ,
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}/replies/{{replyId}}"): READ,
    ("POST", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}/replies"): WRITE,
    ("PATCH", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}/replies/{{replyId}}"): WRITE,
    ("DELETE", f"{DRIVE_PREFIX}/files/{{fileId}}/comments/{{commentId}}/replies/{{replyId}}"): WRITE,
    # --- revisions (metadata-only resources in this mock) ---
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/revisions"): METADATA_READ,
    ("GET", f"{DRIVE_PREFIX}/files/{{fileId}}/revisions/{{revisionId}}"): METADATA_READ,
    ("PATCH", f"{DRIVE_PREFIX}/files/{{fileId}}/revisions/{{revisionId}}"): WRITE,
    ("DELETE", f"{DRIVE_PREFIX}/files/{{fileId}}/revisions/{{revisionId}}"): WRITE,
    # --- changes ---
    ("GET", f"{DRIVE_PREFIX}/changes/startPageToken"): METADATA_READ,
    ("GET", f"{DRIVE_PREFIX}/changes"): METADATA_READ,
    ("POST", f"{DRIVE_PREFIX}/changes/watch"): WATCH,
    # --- shared drives (reads per real Google: drive.readonly|drive; no
    #     metadata.readonly; all mutations are administration -> drive.full) ---
    ("GET", f"{DRIVE_PREFIX}/drives"): READ,
    ("GET", f"{DRIVE_PREFIX}/drives/{{driveId}}"): READ,
    ("POST", f"{DRIVE_PREFIX}/drives"): SHARING,
    ("PATCH", f"{DRIVE_PREFIX}/drives/{{driveId}}"): SHARING,
    ("DELETE", f"{DRIVE_PREFIX}/drives/{{driveId}}"): SHARING,
    ("POST", f"{DRIVE_PREFIX}/drives/{{driveId}}/hide"): SHARING,
    ("POST", f"{DRIVE_PREFIX}/drives/{{driveId}}/unhide"): SHARING,
    # --- channels ---
    ("POST", f"{DRIVE_PREFIX}/channels/stop"): WATCH,
}
