#!/usr/bin/env bash
# Reference solution: find overshared sensitive files and remove bad permissions.
# The agent must distinguish legitimate external shares (e.g., partner collab docs,
# public blog drafts) from problematic overshares on sensitive files.
set -euo pipefail

# Step 1: List all files
files_json=$(gws drive files list --params '{"fields": "files(id,name,mimeType)", "pageSize": 100}')

# Sensitive file names to lock down
SENSITIVE_NAMES=(
  "api-keys.env"
  "Board Meeting Notes - Q1 2026"
  "Employee Salary Data 2026.xlsx"
  "Team Standup Notes.txt"
)

for name in "${SENSITIVE_NAMES[@]}"; do
  # Find the file ID
  file_id=$(echo "$files_json" | python3 -c "
import sys, json
name = '''${name}'''
files = json.load(sys.stdin)['files']
for f in files:
    if f['name'] == name:
        print(f['id'])
        break
")

  if [ -z "$file_id" ]; then
    continue
  fi

  # List permissions and remove overshared ones
  perms_json=$(gws drive permissions list \
    --params "{\"fileId\": \"${file_id}\", \"fields\": \"permissions(id,type,role,emailAddress)\"}")
  echo "$perms_json" | python3 -c "
import sys, json
perms = json.load(sys.stdin)['permissions']
for p in perms:
    if p['role'] != 'owner':
        if p['type'] == 'anyone' or p['type'] == 'user' and p.get('emailAddress', '').split('@')[1] not in ('nexusai.com',):
            print(p['id'])
" | while read -r perm_id; do
    gws drive permissions delete \
      --params "{\"fileId\": \"${file_id}\", \"permissionId\": \"${perm_id}\"}"
  done
done

echo "Done"
