FROM ghcr.io/benchflow-ai/env0:0.2.0

WORKDIR /app
ENV TASK_ROOT=/var/lib/task
ENV NEEDLE_MANIFEST=/data/oracle/manifest.json

COPY example_tasks/multi-mail-cal-sync/data /var/lib/task/data
COPY example_tasks/multi-mail-cal-sync/oracle /var/lib/task/oracle

RUN chmod 700 /var/lib/task && \
    mkdir -p /data/oracle && \
    mock-gmail --db /data/gmail.db seed \
      --task-data /var/lib/task/data \
      --task-name multi-mail-cal-sync \
      --manifest-path /data/oracle/manifest.json && \
    mock-gcal --db /data/gcal.db seed \
      --task-data /var/lib/task/data \
      --task-name multi-mail-cal-sync
RUN chmod 700 /data/oracle

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
