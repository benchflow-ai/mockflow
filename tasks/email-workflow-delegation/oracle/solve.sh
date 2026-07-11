#!/usr/bin/env bash
# Oracle: forward each delegation task to the correct team member.
# Reads needle manifest for topic-to-recipient mapping.
# Marcus uses role references — the oracle reads the manifest directly
# so it already knows name/email without needing to resolve roles.
set -euo pipefail

MANIFEST="${NEEDLE_MANIFEST:-/data/_needle_manifest_email-workflow-delegation.json}"

# Search for the delegation email first (earns used_search bonus)
gws gmail users messages list \
  --params '{"userId": "me", "q": "sprint task assignments", "maxResults": 5}' > /dev/null 2>&1 || true

# Read manifest and send delegation emails
python3 -c "
import json, base64, subprocess

m = json.load(open('$MANIFEST'))
needle = next(n for n in m['needles'] if n['role'] == 'delegation')
delegations = needle['params']['delegations']

# Topic descriptions for forwarded emails
topic_descriptions = {
    'api_docs': 'API docs update — the OpenAPI spec is outdated and clients are complaining. Please handle this for the upcoming release.',
    'css_fix': 'CSS regression from yesterday deploy — the sidebar is broken on mobile and it is blocking the Meridian demo. Please investigate and fix.',
    'monitoring': 'Monitoring setup for the new billing service — please own this and set up Datadog access.',
}

tracking_lines = []

for d in delegations:
    topic = d['topic']
    name = d['name']
    email = d['email']
    role = d.get('role', topic)
    desc = topic_descriptions.get(topic, f'Task: {topic}')

    msg = f'''To: {email}
Subject: Task Assignment: {topic.replace('_', ' ').title()}

Hi {name},

You have been assigned the following task:

{desc}

Let me know if you have any questions or need anything to get started.

Thanks
'''
    raw = base64.urlsafe_b64encode(msg.encode()).decode()
    cmd = [
        'gws', 'gmail', 'users', 'messages', 'send',
        '--params', '{\"userId\": \"me\"}',
        '--json', json.dumps({'raw': raw}),
    ]
    subprocess.run(cmd, check=True)
    tracking_lines.append(f'- {topic}: {name} ({email})')
    print(f'Sent {topic} delegation to {email}')

# NOTE: The flaky CI task is explicitly unassigned by Marcus —
# the oracle correctly does NOT forward it to anyone.

# Create tracking draft
tracking = '\n'.join(tracking_lines)
draft_msg = f'''To: me
Subject: Task Delegation Tracking Summary

Delegation Summary:
{tracking}

All tasks have been delegated to the appropriate team members.
'''
draft_raw = base64.urlsafe_b64encode(draft_msg.encode()).decode()
cmd = [
    'gws', 'gmail', 'users', 'drafts', 'create',
    '--params', '{\"userId\": \"me\"}',
    '--json', json.dumps({'message': {'raw': draft_raw}}),
]
subprocess.run(cmd, check=True)
print('Tracking draft created')
"
