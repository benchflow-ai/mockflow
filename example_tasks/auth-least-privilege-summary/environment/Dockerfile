FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV AUTH_ENABLED=1
ENV AUTH_URL=http://localhost:9000
ENV GMAIL_URL=http://localhost:9001
ENV TASKS_DIR=/tasks

COPY example_tasks/auth-least-privilege-summary/data /tasks/auth-least-privilege-summary/data
COPY example_tasks/auth-least-privilege-summary/data /var/lib/task/data
COPY example_tasks/auth-least-privilege-summary/oracle /var/lib/task/oracle

RUN mock-auth --db /data/auth.db seed --scenario task:auth-least-privilege-summary
RUN mock-gmail --db /data/gmail.db seed --scenario task:auth-least-privilege-summary
RUN chmod -R 700 /tasks /var/lib/task

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
