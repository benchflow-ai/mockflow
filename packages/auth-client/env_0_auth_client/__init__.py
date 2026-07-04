"""auth-client -- middleware for environment resource servers to validate auth JWTs."""

from env_0_auth_client.config import is_auth_enabled
from env_0_auth_client.middleware import Env_0AuthMiddleware
from env_0_auth_client.reporting import report_impersonation
from env_0_auth_client.routing import match_route
from env_0_auth_client.scopes import ScopeMap

__all__ = [
    "Env_0AuthMiddleware",
    "ScopeMap",
    "is_auth_enabled",
    "match_route",
    "report_impersonation",
]
