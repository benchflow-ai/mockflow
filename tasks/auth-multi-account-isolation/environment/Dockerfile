FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001

# The published base image predates auth, so it does not set the auth
# env vars from config.toml — set them explicitly (GMAIL_URL re-stated
# for symmetry; same value the base derives from config.toml).
ENV AUTH_ENABLED=1

# Task seed data
COPY tasks/auth-multi-account-isolation/data /tasks/auth-multi-account-isolation/data
ENV TASKS_DIR=/tasks

# Seed auth: base users (user1/user2) + AUTH_USERS (user_101) +
# AUTH_CLIENTS (work-client/personal-client) + AUTH_CONSENTS from needles.py.
RUN mock-auth --db /data/auth.db seed --scenario task:auth-multi-account-isolation

# Seed gmail: work mailbox (user1) with the contract needles + filler.
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-multi-account-isolation

# The gmail task seeder only seeds the primary work user. Add the personal
# account (user_101, alex.personal@gmail.local) using the env-owned fixture
# from the `multi_account` scenario, then refresh the "initial" snapshot so
# /_admin/diff stays empty pre-agent.
RUN python3 /tasks/auth-multi-account-isolation/data/seed_personal_account.py /data/gmail.db

# Create log dirs expected by BenchFlow verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gmail from tasks/_manifests/env-0.toml.
