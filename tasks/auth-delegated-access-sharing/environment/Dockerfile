FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV AUTH_URL=http://localhost:9000
ENV CALENDAR_URL=http://localhost:9002
ENV DRIVE_URL=http://localhost:9003

# --- Task seed data (verifier/ + oracle/ are uploaded by benchflow) ----------
COPY tasks/auth-delegated-access-sharing/data /tasks/auth-delegated-access-sharing/data
ENV TASKS_DIR=/tasks

# --- Auth integration env ---------------------------------------------------
# The published base lacks the auth env vars, so set them explicitly.
# AUTH_ENABLED=1 makes the gcal/gdrive servers require a Bearer token on
# every API call and verify it against auth's JWKS at AUTH_URL.
ENV AUTH_ENABLED=1

# --- Seed each service from this task's needles.py --------------------------
RUN mock-auth --db /data/auth.db seed --scenario task:auth-delegated-access-sharing
RUN mock-gcal --db /data/gcal.db seed --scenario task:auth-delegated-access-sharing
# Post-seed augmentation: create user1's "Project Plans" calendar (not a built-in
# gcal template) and re-snapshot the gcal "initial" baseline.
RUN python3 /tasks/auth-delegated-access-sharing/data/seed_gcal_extra.py /data/gcal.db
RUN mock-gdrive --db /data/gdrive.db seed --scenario task:auth-delegated-access-sharing

# Create log dirs expected by the verifier/agent
RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Grant agent write access to its log dirs (env source lives in env0)
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-auth, mock-gcal, mock-gdrive from tasks/_manifests/env-0.toml.
