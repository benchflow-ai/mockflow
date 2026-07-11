FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV STRIPE_URL=http://localhost:9007

COPY tasks/stripe-idempotent-no-double-charge/data /tasks/stripe-idempotent-no-double-charge/data
ENV TASKS_DIR=/tasks

# Seed the scenario (auto-discovered from data/stripe_seed.py via TASKS_DIR).
# db_path matches config.toml [stripe].db_path.
RUN mock-stripe --db /data/stripe.db seed --scenario task:stripe-idempotent-no-double-charge

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-stripe from tasks/_manifests/env-0.toml.
