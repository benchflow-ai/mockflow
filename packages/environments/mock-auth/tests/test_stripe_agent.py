"""The stripe-agent confidential client (stripe retrofit).

Verifies the seeded client can mint Stripe-scoped JWTs via both the admin
shortcut (/_admin/issue_token) and a full authorization-code flow, and that
its allowed_scopes bound the grantable set to the Stripe vocabulary + openid.
"""

from __future__ import annotations

import json

import jwt as pyjwt

from .conftest import authorize_params, exchange_code, extract_query, pkce_pair

STRIPE_AGENT = "stripe-agent"
STRIPE_AGENT_SECRET = "stripe-agent-secret"
STRIPE_REDIRECT = "http://localhost:8085/callback"


def _scopes_of(access_token: str) -> set[str]:
    claims = pyjwt.decode(access_token, options={"verify_signature": False})
    return set(str(claims.get("scope", "")).split())


class TestStripeAgentClient:
    def test_client_is_seeded_with_stripe_allowed_scopes(self, client):
        state = client.get("/_admin/state").json()
        clients = {c["client_id"]: c for c in state["oauth_clients"]}
        assert STRIPE_AGENT in clients
        agent = clients[STRIPE_AGENT]
        assert agent["client_type"] == "confidential"
        raw = agent["allowed_scopes"]
        allowed = set(raw) if isinstance(raw, list) else set(json.loads(raw))
        for scope in ("stripe.charges.write", "stripe.customers.read",
                      "stripe.full", "stripe.read_only", "openid"):
            assert scope in allowed

    def test_stripe_default_scenario_registers_the_client(self, client):
        r = client.post("/_admin/seed", json={"scenario": "stripe_default"})
        assert r.status_code == 200, r.text
        assert r.json()["stripe_client"] == STRIPE_AGENT
        state = client.get("/_admin/state").json()
        assert any(c["client_id"] == STRIPE_AGENT for c in state["oauth_clients"])

    def test_issue_token_mints_stripe_charges_write(self, client):
        tok = client.post("/_admin/issue_token", json={
            "client_id": STRIPE_AGENT,
            "user_id": "user1",
            "scopes": ["stripe.charges.write", "stripe.customers.read"],
        }).json()
        assert tok["token_type"] == "Bearer"
        scopes = _scopes_of(tok["access_token"])
        assert "stripe.charges.write" in scopes
        assert "stripe.customers.read" in scopes
        claims = pyjwt.decode(tok["access_token"], options={"verify_signature": False})
        assert claims["client_id"] == STRIPE_AGENT
        assert claims["aud"] == STRIPE_AGENT

    def test_auth_code_flow_mints_stripe_charges_write(self, client):
        verifier, challenge = pkce_pair()
        scope = "openid stripe.charges.write stripe.payment_intents.write"
        client.post("/_admin/auto_consent", json={
            "client_id": STRIPE_AGENT, "user_id": "user1", "scopes": scope.split(),
        })
        r = client.get(
            "/o/oauth2/v2/auth",
            params=authorize_params(scope, client_id=STRIPE_AGENT,
                                    redirect_uri=STRIPE_REDIRECT,
                                    challenge=challenge, login_hint="alex@nexusai.com"),
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        code = extract_query(r.headers["location"])["code"]
        tok = exchange_code(client, code, client_id=STRIPE_AGENT,
                            client_secret=STRIPE_AGENT_SECRET,
                            redirect_uri=STRIPE_REDIRECT, verifier=verifier)
        scopes = _scopes_of(tok["access_token"])
        assert "stripe.charges.write" in scopes
        assert "stripe.payment_intents.write" in scopes
