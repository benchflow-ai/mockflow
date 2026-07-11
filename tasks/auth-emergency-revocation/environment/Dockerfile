FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# Auth wiring — the published base sets service URL only for the older envs,
# so set the auth-related env vars explicitly.
ENV AUTH_ENABLED=1

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/auth-emergency-revocation/data /tasks/auth-emergency-revocation/data
ENV TASKS_DIR=/tasks

# Seed auth (users + 6 clients + 6 consents from this task's needles.py),
# then run the session hook to mint one real access token per active session
# and write the suspicious-sign-in audit trail for unknown-device-x. Finally
# seed gmail's inbox (security alert + filler) from the same needles.py.
RUN mock-auth --db /data/auth.db seed --scenario task:auth-emergency-revocation
RUN python3 /tasks/auth-emergency-revocation/data/seed_sessions.py /data/auth.db
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-emergency-revocation

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
