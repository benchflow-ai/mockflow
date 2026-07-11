FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV STRIPE_URL=http://localhost:9007

# --- Task seed data ---------------------------------------------------------
COPY tasks/stripe-least-privilege-charge/data /tasks/stripe-least-privilege-charge/data
ENV TASKS_DIR=/tasks

# --- Auth integration env ---------------------------------------------------
# The published base lacks the auth env vars, so set them explicitly.
# AUTH_ENABLED=1 makes the stripe server require a Bearer auth JWT on
# every /v1 call; the agent must obtain a scoped token to charge. The issuer
# defaults to http://localhost:9000 (auth's port), which matches
# AUTH_URL below — so the stripe middleware trusts the JWTs auth mints.
ENV AUTH_ENABLED=1

# --- Seed both services -----------------------------------------------------
# stripe uses its built-in `default` dataset (Ada/Grace/Alan + history).
# auth uses this task's needles.py (AUTH_CONSENTS auto-consents user1 ->
# stripe-agent for the full stripe.* set).
RUN mock-stripe --db /data/stripe.db seed --scenario default
RUN mock-auth --db /data/auth.db seed --scenario task:stripe-least-privilege-charge

# Create log dirs expected by the verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-stripe, mock-auth from tasks/_manifests/env-0.toml.
