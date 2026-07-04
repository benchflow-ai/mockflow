FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV TASK_ROOT=/var/lib/task
ENV NEEDLE_MANIFEST=/data/oracle/manifest.json

COPY example_tasks/email-confidential-forward/data /var/lib/task/data
COPY example_tasks/email-confidential-forward/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task
RUN mkdir -p /data/oracle && \
    mock-gmail --db /data/gmail.db seed \
      --task-data /var/lib/task/data \
      --task-name email-confidential-forward \
      --manifest-path /data/oracle/manifest.json
RUN chmod 700 /data/oracle

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
