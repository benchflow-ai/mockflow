FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV STRIPE_URL=http://localhost:9007

COPY example_tasks/stripe-refund-correct-customer/data /tasks/stripe-refund-correct-customer/data
COPY example_tasks/stripe-refund-correct-customer/data /var/lib/task/data
COPY example_tasks/stripe-refund-correct-customer/oracle /var/lib/task/oracle
ENV TASKS_DIR=/tasks

# No auth: this is a capability+safety task on the disabled-mode test key
# (sk_test_env_0_51deterministic). AUTH_ENABLED stays unset so the seeded
# test key is the credential.

RUN mock-stripe --db /data/stripe.db seed --scenario task:stripe-refund-correct-customer
RUN chmod -R 700 /tasks /var/lib/task

# Create log dirs expected by the verifier/agent
RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# NOTE: Daytona doesn't run CMD/ENTRYPOINT. mock-stripe is started by
# BenchFlow from tasks/_manifests/env-0.toml.
