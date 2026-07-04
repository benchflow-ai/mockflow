"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples EXACTLY as
the routes are registered on the FastAPI app (see ``mock_gdoc/api/app.py``).
Values are OR-logic scope lists: ANY one listed scope grants access. Routes
absent from the map (and exempt prefixes like /_admin, /health, /dev, /doc,
the web root "/") require a valid token but no particular scope.

Scope names are the bare auth names (``docs.readonly``, not full Google
URLs); the contract-pinned Docs rules are:

- document reads (documents.get)         -> docs.readonly | docs.full
- ALL document mutations (create,
  batchUpdate)                           -> docs.full only

gdoc also serves comments and permissions under /v1/documents/* -- in
real Google these are DRIVE API (v3) resources (file metadata), not Docs API
endpoints. Decision (documented per mission): these drive-file-metadata proxy
routes ALSO accept the Drive scopes:

- comment / permission reads             -> + drive.readonly | drive.full
- comment / permission mutations         -> docs.full | drive.full

``drive.file`` / ``drive.metadata.readonly`` are deliberately NOT accepted:
this mock has no notion of per-app file provenance, and permissions/comments
reads expose more than bare metadata.

This module deliberately has NO env_0_auth_client import so that gdoc
works unchanged when auth-client is not installed.

Coverage of every registered /v1 route is enforced by
``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

DOCS_PREFIX = "/v1"
_D = f"{DOCS_PREFIX}/documents"

DOCS_READONLY = "docs.readonly"
DOCS_FULL = "docs.full"
DRIVE_READONLY = "drive.readonly"
DRIVE_FULL = "drive.full"

# Document body reads: Docs API proper (contract-pinned pair).
DOC_READ = [DOCS_READONLY, DOCS_FULL]
# Document mutations: docs.full ONLY (contract: all mutations need docs.full).
DOC_WRITE = [DOCS_FULL]
# Comments / permissions are Drive-file metadata proxies: reads additionally
# accept the Drive read scopes, mutations accept drive.full alongside docs.full.
META_READ = [DOCS_READONLY, DOCS_FULL, DRIVE_READONLY, DRIVE_FULL]
META_WRITE = [DOCS_FULL, DRIVE_FULL]

SCOPE_MAP: ScopeMap = {
    # --- documents (Docs API proper) ---
    ("GET", f"{_D}/{{documentId}}"): DOC_READ,
    ("POST", _D): DOC_WRITE,  # documents.create
    ("POST", f"{_D}/{{documentId}}:batchUpdate"): DOC_WRITE,
    # --- comments (Drive API v3 resource, proxied under /v1/documents) ---
    ("GET", f"{_D}/{{documentId}}/comments"): META_READ,
    ("POST", f"{_D}/{{documentId}}/comments"): META_WRITE,
    ("GET", f"{_D}/{{documentId}}/comments/{{commentId}}"): META_READ,
    ("PATCH", f"{_D}/{{documentId}}/comments/{{commentId}}"): META_WRITE,
    ("DELETE", f"{_D}/{{documentId}}/comments/{{commentId}}"): META_WRITE,
    ("POST", f"{_D}/{{documentId}}/comments/{{commentId}}/resolve"): META_WRITE,
    ("POST", f"{_D}/{{documentId}}/comments/{{commentId}}/reopen"): META_WRITE,
    ("POST", f"{_D}/{{documentId}}/comments/{{commentId}}/replies"): META_WRITE,
    ("DELETE", f"{_D}/{{documentId}}/comments/{{commentId}}/replies/{{replyId}}"): META_WRITE,
    # --- permissions (Drive API v3 resource, proxied under /v1/documents) ---
    ("GET", f"{_D}/{{documentId}}/permissions"): META_READ,
    ("POST", f"{_D}/{{documentId}}/permissions"): META_WRITE,
    ("PATCH", f"{_D}/{{documentId}}/permissions/{{permissionId}}"): META_WRITE,
    ("DELETE", f"{_D}/{{documentId}}/permissions/{{permissionId}}"): META_WRITE,
}
