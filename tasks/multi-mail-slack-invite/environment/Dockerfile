FROM ghcr.io/benchflow-ai/env0:0.2.0

# Compatibility URLs used by the copied benchmark contract.
ENV GMAIL_URL=http://localhost:9001
ENV SLACK_URL=http://localhost:9005

# Task seed data (verifier/ + oracle/ uploaded by benchflow at runtime)
COPY tasks/multi-mail-slack-invite/data /tasks/multi-mail-slack-invite/data
ENV TASKS_DIR=/tasks

# Seed Gmail with SkillsBench contributor emails
RUN mock-gmail --db /data/gmail.db seed --scenario task:multi-mail-slack-invite

# Seed Slack with contributor users (channels to be created by agent)
RUN mock-slack --db /data/slack.db seed --scenario task:multi-mail-slack-invite

RUN chmod -R 700 /tasks

RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts

# Lock all sensitive directories (root-only access)
RUN chown agent:agent /logs/agent /logs/artifacts

# Mock Slack tokens for the agent
ENV SLACK_BOT_TOKEN=xoxb-mock-bot-token
ENV SLACK_USER_TOKEN=xoxp-mock-user-token

# BenchFlow starts mock-gmail, mock-slack from tasks/_manifests/env-0.toml.
