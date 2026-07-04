FROM ghcr.io/benchflow-ai/env0:0.1.0

WORKDIR /app
ENV DISCORD_URL=http://localhost:9006

COPY example_tasks/discord-incident-followup/data /tasks/discord-incident-followup/data
COPY example_tasks/discord-incident-followup/data /var/lib/task/data
COPY example_tasks/discord-incident-followup/oracle /var/lib/task/oracle
ENV TASKS_DIR=/tasks

RUN mock-discord --db /data/discord.db seed --scenario default
RUN chmod -R 700 /tasks /var/lib/task

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts
RUN chown agent:agent /logs/agent /logs/artifacts

# BenchFlow starts mock-discord from tasks/_manifests/env-0.toml.
