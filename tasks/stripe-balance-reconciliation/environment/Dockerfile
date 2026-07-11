FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV STRIPE_URL=http://localhost:9007

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/stripe-balance-reconciliation/data /tasks/stripe-balance-reconciliation/data
ENV TASKS_DIR=/tasks

# Seed at build (discovers data/stripe_seed.py via the task:<name> scenario).
RUN mock-stripe --db /data/stripe.db seed --scenario task:stripe-balance-reconciliation

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-stripe from tasks/_manifests/env-0.toml.
