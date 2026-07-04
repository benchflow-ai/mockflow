FROM ghcr.io/benchflow-ai/env0:0.1.0

COPY tasks/multi-doc-slack-spec-drift/data /tasks/multi-doc-slack-spec-drift/data
ENV TASKS_DIR=/tasks

RUN mock-gdrive --db /data/gdrive.db seed --scenario task:multi-doc-slack-spec-drift
RUN mock-gdoc --db /data/gdoc.db seed --from-gdrive /data/gdrive.db
RUN mock-slack --db /data/slack.db seed --scenario task:multi-doc-slack-spec-drift

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts
