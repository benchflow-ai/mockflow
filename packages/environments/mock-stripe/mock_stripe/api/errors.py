"""Stripe error envelope: {"error": {"type", "code", "message", "param", ...}}."""

from __future__ import annotations


def _doc_url_for(code: str | None) -> str | None:
    if not code:
        return None
    return f"https://stripe.com/docs/error-codes/{code.replace('_', '-')}"


# Sentinel so callers can pass `doc_url=None` to SUPPRESS the auto-derived
# doc_url (real Stripe omits doc_url on some errors, e.g. invalid API key).
# Without it, `None` is indistinguishable from "not provided" and the code
# would always fall back to _doc_url_for(code).
_UNSET = object()


class StripeError(Exception):
    """Raise from any route/dependency; the app-level handler renders the envelope."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        type: str = "invalid_request_error",
        code: str | None = None,
        param: str | None = None,
        decline_code: str | None = None,
        charge: str | None = None,
        payment_intent: dict | None = None,
        payment_method: dict | None = None,
        doc_url: str | None | object = _UNSET,
        request_log_url: str | None = None,
        include_param_null: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.type = type
        self.code = code
        self.param = param
        self.decline_code = decline_code
        self.charge = charge
        self.payment_intent = payment_intent
        self.payment_method = payment_method
        # `_UNSET` -> derive from code; explicit None -> suppress; str -> use it.
        self.doc_url = _doc_url_for(code) if doc_url is _UNSET else doc_url
        self.request_log_url = request_log_url
        self.include_param_null = include_param_null

    def to_body(self) -> dict:
        err: dict = {"type": self.type, "message": self.message}
        if self.code is not None:
            err["code"] = self.code
        if self.param is not None or self.include_param_null:
            err["param"] = self.param
        if self.decline_code is not None:
            err["decline_code"] = self.decline_code
        if self.charge is not None:
            err["charge"] = self.charge
        if self.doc_url is not None:
            err["doc_url"] = self.doc_url
        if self.request_log_url is not None:
            err["request_log_url"] = self.request_log_url
        if self.payment_intent is not None:
            err["payment_intent"] = self.payment_intent
        if self.payment_method is not None:
            err["payment_method"] = self.payment_method
        return {"error": err}


def resource_missing(kind: str, obj_id: str) -> StripeError:
    """404 — `{"type": "invalid_request_error", "code": "resource_missing", "param": "id"}`."""
    return StripeError(
        404,
        f"No such {kind}: '{obj_id}'",
        code="resource_missing",
        param="id",
    )


def missing_param(param: str) -> StripeError:
    return StripeError(
        400,
        f"Missing required param: {param}.",
        code="parameter_missing",
        param=param,
    )


def unknown_param(param: str) -> StripeError:
    return StripeError(
        400,
        f"Received unknown parameter: {param}",
        code="parameter_unknown",
        param=param,
    )


def invalid_integer(param: str, value) -> StripeError:
    return StripeError(400, f"Invalid integer: {value}", param=param)


def check_unknown_params(data: dict, allowed: set[str]) -> None:
    """Reject unknown top-level POST params the way Stripe does."""
    allowed = allowed | {"expand"}
    for key in data:
        if key not in allowed:
            raise unknown_param(key)


def as_int(data: dict, param: str, *, required: bool = False, default: int | None = None) -> int | None:
    if param not in data or data[param] in ("", None):
        if required:
            raise missing_param(param)
        return default
    value = data[param]
    if isinstance(value, bool):
        raise invalid_integer(param, value)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise invalid_integer(param, value)


def as_bool(data: dict, param: str, default: bool | None = None) -> bool | None:
    if param not in data:
        return default
    value = data[param]
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise StripeError(400, f"Invalid boolean: {value}", param=param)
