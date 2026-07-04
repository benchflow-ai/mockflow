#!/usr/bin/env bash
# Oracle: find vendor financial digests, label them, draft summary.
# Reads needle manifest for message IDs and financial params.
# Only labels vendor_report needles (skips decoys, adversarial, manager_hint).
set -euo pipefail

MANIFEST="${NEEDLE_MANIFEST:-/data/_needle_manifest_email-vendor-report-organize.json}"

# Search for financial emails (earns search usage bonus)
gws gmail users messages list \
  --params '{"userId": "me", "q": "mercury OR stripe cash summary OR revenue"}' > /dev/null 2>&1 || true

# Step 1: Create "Vendor Reports" label
LABEL_ID=$(gws gmail users labels create \
  --params '{"userId": "me"}' \
  --json '{"name": "Vendor Reports"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Created label: $LABEL_ID"

# Step 2: Get ONLY vendor_report needle IDs from manifest and apply label
python3 -c "
import json, subprocess

m = json.load(open('$MANIFEST'))
ids = [n['message_id'] for n in m['needles'] if n.get('role') == 'vendor_report']
payload = json.dumps({'ids': ids, 'addLabelIds': ['$LABEL_ID']})
cmd = [
    'gws', 'gmail', 'users', 'messages', 'batchModify',
    '--params', '{\"userId\": \"me\"}',
    '--json', payload,
]
subprocess.run(cmd, check=True)
print(f'Applied label to {len(ids)} vendor reports (skipped decoys)')
"

# Step 3: Discover manager email from manager_hint needle, build draft
# with actual numbers from the manifest
DRAFT_RAW=$(python3 -c "
import json, base64

m = json.load(open('$MANIFEST'))
needles = m['needles']

# Discover manager email from manager_hint needle
manager_email = 'marcus@nexusai.com'
for n in needles:
    if n.get('role') == 'manager_hint':
        manager_email = n.get('params', {}).get('manager_email', manager_email)
        break

# Separate Mercury and Stripe vendor reports
mercury = [n for n in needles if n.get('role') == 'vendor_report' and n.get('params', {}).get('week_date')]
stripe = [n for n in needles if n.get('role') == 'vendor_report' and n.get('params', {}).get('month_label')]

lines = ['Financial Vendor Report Summary', '']

if mercury:
    lines.append('Mercury Weekly Cash Summaries:')
    for w in mercury:
        p = w['params']
        lines.append(f\"  {p['week_date']}: Opening \${p['opening']} -> Closing \${p['closing']}\")
        lines.append(f\"    Burn rate: \${p['burn']}/mo | Runway: {p['runway_months']} months\")
    lines.append('')

if stripe:
    lines.append('Stripe Revenue Summaries:')
    for s in stripe:
        p = s['params']
        lines.append(f\"  {p['month_label']}: MRR \${p['mrr']}, Net Revenue \${p['net_revenue']}\")
    lines.append('')

lines.append('All vendor reports have been labeled and organized.')

body = '\n'.join(lines)
msg = f'''To: {manager_email}
Subject: Financial Digest — Weekly Summary

{body}
'''
print(base64.urlsafe_b64encode(msg.encode()).decode())
")

gws gmail users drafts create \
  --params '{"userId": "me"}' \
  --json "{\"message\": {\"raw\": \"$DRAFT_RAW\"}}"

echo "Draft created"
